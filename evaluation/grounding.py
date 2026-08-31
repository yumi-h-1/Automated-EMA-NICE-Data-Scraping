"""Checks that need no hand-labelled answers.

Every indication field is an *extraction*: the correct answer is already on the
page, word for word. So two things can be verified with no gold set at all —

  * grounding — is every phrase the model returned actually present in the
    source page? Anything that is not was invented.
  * coverage  — for the two fields whose source markup is unambiguous (bold =
    added, strikethrough = removed), BeautifulSoup can pull the reference text
    directly, so the model can be scored against it automatically.

The summary column needs its own version of the same idea, because it is the one
output that is allowed to rephrase:

  * retrieval recall     — of the spans EMA marked up, how many did the search
    actually surface? The bold markup *is* the ground truth for what changed, so
    this needs no labels either.
  * supported fraction   — how much of the summary's vocabulary is in the
    passages it was given.
  * citation rate        — how many of its sentences cite a passage that was
    really retrieved.

Whatever fails these checks is the (short) list worth reading by hand.
"""

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))

from http_utils import fetch_soup, page_text  # noqa: E402
from rag import marked_spans, to_markers  # noqa: E402

from metrics import citation_rate, is_empty, normalise, supported_fraction  # noqa: E402

# Bold text EMA puts on every variation page, unrelated to any indication.
BOILERPLATE = ('First published:', 'This page was last updated on', 'European Medicines Agency')

GROUNDED = 0.95
PARTIAL = 0.60


def coverage(prediction, source_text):
    """Fraction of the prediction's words that appear, in order, in the source.

    1.0 means every word was copied from the page; a low score means the model
    wrote something the page does not contain.
    """
    pred_tokens = normalise(prediction).split()
    source_tokens = normalise(source_text, strip_prefix=False).split()
    if not pred_tokens:
        return 1.0
    if not source_tokens:
        return 0.0

    matcher = SequenceMatcher(None, pred_tokens, source_tokens, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(pred_tokens)


def classify(score):
    if score >= GROUNDED:
        return 'grounded'
    if score >= PARTIAL:
        return 'partial'
    return 'ungrounded'


def marked_up_fragments(soup, tag):
    """The text EMA marked as added (<strong>) or removed (<s>) on a variation page.

    These fragments are frequently mid-sentence ('an', '-based regimen'), because
    EMA marks up a character-level diff rather than whole indications. That is
    exactly why the pipeline asks a model to stitch them together — but the
    fragments themselves are an exact reference for what it had to work with.
    """
    fragments = []
    for element in soup.find_all(tag):
        text = element.get_text(' ', strip=True)
        if text and not any(text.startswith(b) for b in BOILERPLATE):
            fragments.append(text)
    return fragments


def check_against_markup(prediction, soup, tag):
    """Score one bold/strikethrough field against the markup it came from."""
    fragments = marked_up_fragments(soup, tag)
    reference = ', '.join(fragments)

    if not fragments:
        # Nothing was marked up, so the only correct answer is "nothing".
        return {
            'verdict': 'grounded' if is_empty(_strip_answer(prediction)) else 'ungrounded',
            'coverage': 1.0 if is_empty(_strip_answer(prediction)) else 0.0,
            'reference': '',
            'note': 'no marked-up text on the page',
        }

    score = coverage(prediction, reference)
    missed = [f for f in fragments if normalise(f) and normalise(f) not in normalise(prediction)]
    return {
        'verdict': classify(score),
        'coverage': score,
        'reference': reference,
        'note': f'{len(missed)}/{len(fragments)} fragments not reproduced' if missed else '',
    }


def check_against_page(prediction, source_text):
    """Score a free-text extraction against the full text of its source page."""
    if is_empty(_strip_answer(prediction)):
        return {'verdict': 'empty', 'coverage': 0.0, 'reference': '', 'note': 'no answer'}
    score = coverage(prediction, source_text)
    return {'verdict': classify(score), 'coverage': score, 'reference': '', 'note': ''}


_ANSWER_PREFIX = re.compile(r'^[^:\n]{1,60}:\s*')


def _strip_answer(prediction):
    """Drop the 'Medicine Name:' prefix the prompts ask the model to add."""
    return _ANSWER_PREFIX.sub('', str(prediction or '').strip())


def report(dataset, fetch=fetch_soup):
    """Run every no-label check over a produced dataset.

    `dataset` is the DataFrame the pipeline writes. Returns a list of findings,
    one per (medicine, field) that is worth a human glance.
    """
    findings = []

    for _, row in dataset.iterrows():
        name = row.get('Product Name', '?')

        variation_urls = [u.strip() for u in str(row.get('variation_url', '')).split(',') if u.strip()]
        if variation_urls:
            try:
                variation_soup = fetch(variation_urls[0])
                for field, tag in (('New indication HTML', 'strong'),
                                   ('Removed indication HTML', 's')):
                    if field in row.index:
                        result = check_against_markup(row[field], variation_soup, tag)
                        findings.append({'Product Name': name, 'field': field, **result})
            except Exception as e:
                findings.append({'Product Name': name, 'field': 'variation page',
                                 'verdict': 'unchecked', 'coverage': 0.0,
                                 'reference': '', 'note': str(e)})

        if 'Full Indication' in row.index and row.get('epar_url'):
            try:
                source = page_text(fetch(row['epar_url']))
                result = check_against_page(row['Full Indication'], source)
                findings.append({'Product Name': name, 'field': 'Full Indication', **result})
            except Exception as e:
                findings.append({'Product Name': name, 'field': 'Full Indication',
                                 'verdict': 'unchecked', 'coverage': 0.0,
                                 'reference': '', 'note': str(e)})

    return findings


def summarise(findings):
    """Counts per field and verdict, for the console."""
    summary = {}
    for finding in findings:
        key = finding['field']
        summary.setdefault(key, {})
        summary[key][finding['verdict']] = summary[key].get(finding['verdict'], 0) + 1
    return summary


# --- the summary column, still with no labels --------------------------------

def expected_spans(row, pages):
    """Everything EMA marked up on one medicine's variation pages."""
    spans = []
    for url in str(row.get('variation_url', '')).split(','):
        url = url.strip()
        if not url or url == 'N/A' or url not in pages:
            continue
        document = [{'text': to_markers(pages[url]), 'metadata': {}}]
        for marker in ('ADDED', 'REMOVED'):
            for span in marked_spans(document, marker):
                if span not in spans:
                    spans.append(span)
    return spans


def check_retrieval(dataset, retrieval_log, pages):
    """Did the search surface the change EMA marked up?

    One finding per medicine that had a marked-up change; a medicine given a
    first authorisation has no diff, so there is no recall to measure and it is
    left out rather than scored 1.0.
    """
    findings = []

    for _, row in dataset.iterrows():
        name = row.get('Product Name', '?')
        expected = [span for span in expected_spans(row, pages) if normalise(span)]
        if not expected:
            continue

        chunks = retrieval_log.get(name, [])
        retrieved = {normalise(span) for span in
                     marked_spans(chunks, 'ADDED') + marked_spans(chunks, 'REMOVED')}
        hits = [span for span in expected if normalise(span) in retrieved]

        findings.append({
            'Product Name': name,
            'expected': len(expected),
            'retrieved': len(hits),
            'recall': len(hits) / len(expected),
            'missed': [span for span in expected if span not in hits][:3],
        })

    return findings


def check_summaries(dataset, retrieval_log):
    """Is each summary actually built out of the passages it was given?"""
    from rag import format_context

    findings = []

    for _, row in dataset.iterrows():
        name = row.get('Product Name', '?')
        summary = row.get('What changed')
        if is_empty(summary):
            continue

        chunks = retrieval_log.get(name, [])
        context = format_context(chunks)
        score = supported_fraction(summary, context)

        findings.append({
            'Product Name': name,
            'verdict': classify(score),
            'supported_fraction': score,
            'citation_rate': citation_rate(summary, len(chunks)),
            'detail': str(summary)[:160],
        })

    return findings


def mean_recall(findings):
    """Mean retrieval recall over the medicines that had something to find."""
    if not findings:
        return None
    return sum(finding['recall'] for finding in findings) / len(findings)
