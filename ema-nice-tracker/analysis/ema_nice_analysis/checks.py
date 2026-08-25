"""Quality checks that need no hand-labelled answers.

Every indication field is an extraction: the correct answer is already on the
page, word for word. That makes two things verifiable with no gold set:

  * grounding  - is every phrase the model returned actually in the source?
  * agreement  - do the dataset's dates and classifications match EMA's own
                 published exports?

Whatever fails is the short list worth reading by hand.
"""

from difflib import SequenceMatcher

from .lookup import post_authorisation_table, medicines_table, row_for
from .schema import MISSING
from .text import is_empty, normalise

GROUNDED = 0.95
PARTIAL = 0.60


def coverage(prediction, source):
    """Fraction of the prediction's words that appear, in order, in the source.

    1.0 means every word was copied off the page; a low score means the model
    wrote something the page does not contain.
    """
    predicted = normalise(prediction).split()
    available = normalise(source, drop_prefix=False).split()
    if not predicted:
        return 1.0
    if not available:
        return 0.0

    matcher = SequenceMatcher(None, predicted, available, autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks()) / len(predicted)


def verdict(score):
    if score >= GROUNDED:
        return 'grounded'
    if score >= PARTIAL:
        return 'partial'
    return 'ungrounded'


def check_grounding(dataset, crawl):
    """Check every extracted span against the page it was taken from."""
    by_name = {m['productName']: m for m in crawl['medicines']}
    findings = []

    for _, row in dataset.iterrows():
        medicine = by_name.get(row['Product Name'])
        if medicine is None:
            continue

        variation_text = ' '.join((medicine.get('variationHtml') or {}).values())
        sources = {
            'Full Indication': medicine.get('indicationHtml') or '',
            # The marked-up fragments are an exact record of what EMA changed.
            'New indication HTML': ' '.join(medicine.get('markedUpAdded', [])) or variation_text,
            'Removed indication HTML': ' '.join(medicine.get('markedUpRemoved', [])) or variation_text,
        }

        for field, source in sources.items():
            answer = row.get(field, MISSING)
            if is_empty(answer):
                continue
            if not source:
                findings.append({'Product Name': row['Product Name'], 'field': field,
                                 'verdict': 'no source', 'coverage': 0.0,
                                 'detail': 'the model answered but the page had nothing marked up'})
                continue

            score = coverage(answer, source)
            findings.append({'Product Name': row['Product Name'], 'field': field,
                             'verdict': verdict(score), 'coverage': score,
                             'detail': str(answer)[:160]})

    return findings


def check_against_ema_tables(dataset, cache_dir='.'):
    """Compare the dataset with EMA's own published exports."""
    post_auth = post_authorisation_table(cache_dir)
    medicines = medicines_table(cache_dir)
    findings = []

    for _, row in dataset.iterrows():
        name = row['Product Name']
        key = name.lower().replace(' ', '-')

        if row.get('Initial Approval') == 'Extension':
            record = row_for(post_auth, key)
            if record is None:
                findings.append({'Product Name': name, 'check': 'extension listed by EMA',
                                 'result': 'missing',
                                 'detail': 'classified as an extension but absent from EMA\'s '
                                           'post-authorisation table'})
            else:
                findings.append(_compare_dates(
                    name, 'CHMP opinion date',
                    row.get('CHMP Opinion Date'),
                    record.get('Post-authorisation opinion date'),
                ))

        record = row_for(medicines, key)
        if record is not None:
            findings.append(_compare_dates(
                name, 'Commission decision date',
                row.get('Decision date'),
                record.get('European Commission decision date'),
            ))

    return findings


#: Formats EMA and the crawler use, tried in order.
_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %B %Y', '%d %b %Y')


def _compare_dates(name, check, ours, theirs):
    from datetime import date, datetime

    def parse(value):
        if value is None or (isinstance(value, float) and value != value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text or text == MISSING:
            return None
        # Excel round-trips dates as '2026-07-23 00:00:00'.
        text = text.split(' 00:00:00')[0]
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    mine, published = parse(ours), parse(theirs)
    if mine is None and published is None:
        return {'Product Name': name, 'check': check, 'result': 'unchecked',
                'detail': 'neither side has a date'}
    if mine == published:
        return {'Product Name': name, 'check': check, 'result': 'match', 'detail': str(published)}
    return {'Product Name': name, 'check': check, 'result': 'mismatch',
            'detail': f'dataset {mine}, EMA published {published}'}


def summarise(findings, key):
    counts = {}
    for finding in findings:
        counts[finding[key]] = counts.get(finding[key], 0) + 1
    return counts
