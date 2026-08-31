"""Metrics for the LLM outputs in this pipeline.

The pipeline asks the model for three different kinds of answer, and they need
three different kinds of metric:

  1. Verbatim span extraction (the four indication fields). The model is meant to
     copy wording out of the page, not to paraphrase it, so the headline number
     is exact match after normalisation. ROUGE-L is reported alongside it as a
     "how close was the miss" measure, and token precision/recall separate the
     two failure modes ROUGE-L F1 hides: text the model invented (low precision)
     versus text it dropped (low recall).
  2. A date ('EMA date for extension'). Only exact match means anything here;
     a ROUGE score on a date string is noise.
  3. A yes/no judgement (the NICE similarity fields, 'Search Result in NICE').
     This is binary classification: accuracy, precision, recall, F1 and Cohen's
     kappa, since class balance is usually skewed.
"""

import re
import unicodedata
from collections import Counter
from datetime import datetime

from rouge_score import rouge_scorer

_SCORER = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)

# The extraction prompts ask for 'Medicine Name: <indication>'.
_ANSWER_PREFIX = re.compile(r'^[a-z0-9 /\-\']{1,60}:\s*')
_NON_ALNUM = re.compile(r'[^a-z0-9 ]+')
_WHITESPACE = re.compile(r'\s+')

# Answers that mean "the model found nothing".
EMPTY_ANSWERS = {'', 'nan', 'n/a', 'na', 'none', 'i dont know',
                 'error', 'error fetching or processing the page'}

_DATE_FORMATS = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d %B %Y', '%d %b %Y')


def normalise(text, strip_prefix=True):
    """Lower-case, drop the 'Medicine Name:' prefix, punctuation and extra space."""
    # Blank cells arrive from pandas as NaN, whose str() is 'nan' — treat those,
    # and the model's own no-answer replies, as empty.
    if text is None or (isinstance(text, float) and text != text):
        return ''
    text = unicodedata.normalize('NFKC', str(text)).strip().lower()
    if text == 'nan':
        return ''
    if strip_prefix:
        text = _ANSWER_PREFIX.sub('', text)
    text = _NON_ALNUM.sub(' ', text)
    return _WHITESPACE.sub(' ', text).strip()


def is_empty(text):
    """Whether an answer means "nothing found".

    The comparison runs *before* punctuation is stripped. `normalise` turns
    'N/A' into 'n a', which matches nothing in EMPTY_ANSWERS — so every 'N/A'
    used to count as a real answer, and `to_label` read its leading 'n' as an
    explicit "No".
    """
    if text is None or (isinstance(text, float) and text != text):
        return True
    plain = _WHITESPACE.sub(' ', str(text).strip().lower()).rstrip('.')
    # The model writes "I don't know."; both apostrophes turn up in practice.
    plain = plain.replace("'", '').replace('\u2019', '')
    return (plain in EMPTY_ANSWERS
            or _ANSWER_PREFIX.sub('', plain).rstrip('.') in EMPTY_ANSWERS)


# --- 1. verbatim span extraction --------------------------------------------

def span_scores(prediction, reference):
    """Per-example scores for one extracted span."""
    pred, ref = normalise(prediction), normalise(reference)

    # Both blank is a correct "nothing to extract"; one blank is a clear miss.
    if not ref and not pred:
        return {'exact_match': 1.0, 'rouge1_f': 1.0, 'rouge2_f': None,
                'rougeL_f': 1.0, 'precision': 1.0, 'recall': 1.0}
    if not ref or not pred:
        return {'exact_match': 0.0, 'rouge1_f': 0.0, 'rouge2_f': None,
                'rougeL_f': 0.0, 'precision': 0.0, 'recall': 0.0}

    rouge = _SCORER.score(ref, pred)
    pred_counts, ref_counts = Counter(pred.split()), Counter(ref.split())
    overlap = sum((pred_counts & ref_counts).values())

    return {
        'exact_match': float(pred == ref),
        'rouge1_f': rouge['rouge1'].fmeasure,
        # A bigram score needs at least two reference tokens to mean anything.
        'rouge2_f': rouge['rouge2'].fmeasure if len(ref.split()) > 1 else None,
        'rougeL_f': rouge['rougeL'].fmeasure,
        'precision': overlap / sum(pred_counts.values()),
        'recall': overlap / sum(ref_counts.values()),
    }


def span_report(predictions, references):
    """Mean scores over a list of (prediction, reference) pairs."""
    pairs = [span_scores(p, r) for p, r in zip(predictions, references)]
    if not pairs:
        return {}
    report = {'n': len(pairs)}
    for key in pairs[0]:
        scored = [p[key] for p in pairs if p[key] is not None]
        if scored:
            report[key] = sum(scored) / len(scored)
    return report


# --- 2. dates ----------------------------------------------------------------

def parse_date(value):
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def date_report(predictions, references):
    """Exact-match accuracy over dates, tolerant of formatting differences."""
    total = correct = unparsed = 0
    for pred, ref in zip(predictions, references):
        if is_empty(ref):
            continue
        total += 1
        pred_date, ref_date = parse_date(pred), parse_date(ref)
        if pred_date is None:
            unparsed += 1
        elif ref_date is not None and pred_date == ref_date:
            correct += 1
    if total == 0:
        return {'n': 0}
    return {'n': total, 'accuracy': correct / total, 'unparseable_rate': unparsed / total}


# --- 3. yes/no judgements ----------------------------------------------------

def to_label(value):
    """Map a free-text yes/no answer onto True/False, or None if unusable."""
    if is_empty(value):
        return None
    text = normalise(value, strip_prefix=False)
    if not text:
        return None
    first = text.split()[0]
    if first in ('yes', 'y', 'true', '1'):
        return True
    if first in ('no', 'n', 'false', '0'):
        return False
    return None


def binary_report(predictions, references):
    """Accuracy, precision/recall/F1 for the 'Yes' class, and Cohen's kappa."""
    pairs = [(to_label(p), to_label(r)) for p, r in zip(predictions, references)]
    pairs = [(p, r) for p, r in pairs if r is not None]
    if not pairs:
        return {'n': 0}

    unusable = sum(1 for p, _ in pairs if p is None)
    tp = sum(1 for p, r in pairs if p is True and r is True)
    fp = sum(1 for p, r in pairs if p is True and r is False)
    fn = sum(1 for p, r in pairs if p is not True and r is True)
    tn = sum(1 for p, r in pairs if p is False and r is False)
    n = len(pairs)

    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # Cohen's kappa: agreement corrected for what chance alone would produce.
    p_yes = ((tp + fp) / n) * ((tp + fn) / n)
    p_no = ((tn + fn) / n) * ((tn + fp) / n)
    chance = p_yes + p_no
    kappa = (accuracy - chance) / (1 - chance) if chance < 1 else 0.0

    return {'n': n, 'accuracy': accuracy, 'precision': precision, 'recall': recall,
            'f1': f1, 'kappa': kappa, 'unparseable_rate': unusable / n}
