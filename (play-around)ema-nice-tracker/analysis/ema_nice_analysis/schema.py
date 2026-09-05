"""The shape of the published dataset.

Column names are kept identical to the original spreadsheet so existing
analyses keep working against the new tool's output.
"""

IDENTIFICATION = [
    'Product Name', 'INN', 'Marketing authorisation holder',
    'epar_url', 'variation_url', 'MH_url',
]

CLINICAL = [
    'Full Indication', 'New indication HTML', 'Removed indication HTML',
    'New indication PDF', 'Therapy class', 'Therapy Area', 'Cancer', 'Orphan',
]

DATES = [
    'Initial Approval', 'CHMP Opinion Date', 'Decision date',
    'EMA date for extension', 'title', 'date',
]

NICE = [
    'Search Result in NICE', 'NICE_url',
    'Full Indication Similarity', 'New Indication HTML Similarity',
    'New Indication PDF Similarity',
]

COLUMNS = IDENTIFICATION + CLINICAL + DATES + NICE

#: Columns that must never be empty. Anything missing here means the crawler
#: read the wrong part of the page, not that the data does not exist.
REQUIRED = ['Product Name', 'INN', 'Marketing authorisation holder', 'epar_url']

#: Free-text fields the model extracts verbatim from a page.
EXTRACTED_SPANS = [
    'Full Indication', 'New indication HTML',
    'Removed indication HTML', 'New indication PDF',
]

#: Fields where the model returns a yes/no judgement.
JUDGEMENTS = [
    'Full Indication Similarity', 'New Indication HTML Similarity',
    'New Indication PDF Similarity',
]

MISSING = 'N/A'
