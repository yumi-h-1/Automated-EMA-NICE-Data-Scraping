"""Normalising model answers so they can be compared with source text."""

import re
import unicodedata

#: The extraction prompts ask for 'Medicine Name: <answer>'.
ANSWER_PREFIX = re.compile(r'^[^:\n]{1,60}:\s*')
NON_ALNUM = re.compile(r'[^a-z0-9 ]+')
WHITESPACE = re.compile(r'\s+')

#: Answers that mean "the model found nothing".
EMPTY_ANSWERS = {
    '', 'nan', 'n/a', 'na', 'none', 'i dont know', 'not stated',
    'error', 'error fetching or processing the page',
}


def strip_prefix(text):
    return ANSWER_PREFIX.sub('', str(text or '').strip())


def normalise(text, drop_prefix=True):
    """Lower-case, drop the answer prefix, punctuation and repeated spaces."""
    if text is None or (isinstance(text, float) and text != text):
        return ''
    text = unicodedata.normalize('NFKC', str(text)).strip().lower()
    if text == 'nan':
        return ''
    if drop_prefix:
        text = ANSWER_PREFIX.sub('', text)
    return WHITESPACE.sub(' ', NON_ALNUM.sub(' ', text)).strip()


def is_empty(text):
    """Whether an answer means "nothing found".

    The test runs before punctuation is stripped: `normalise` would turn 'N/A'
    into 'n a', which no longer matches anything in EMPTY_ANSWERS.
    """
    if text is None or (isinstance(text, float) and text != text):
        return True
    plain = WHITESPACE.sub(' ', str(text).strip().lower()).rstrip('.')
    # The model writes "I don't know."; the curly and straight apostrophes both
    # turn up, so neither is worth keeping for this comparison.
    plain = plain.replace("'", '').replace('\u2019', '')
    return plain in EMPTY_ANSWERS or strip_prefix(plain).rstrip('.') in EMPTY_ANSWERS
