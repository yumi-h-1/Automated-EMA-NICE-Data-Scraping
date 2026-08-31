"""End-to-end assembly of the EMA dataset for the latest CHMP meeting."""

import pandas as pd

from batch import (
    process_medicines_and_get_indications,
    process_medicines_and_new_indications_html,
    process_medicines_and_removed_indications_html,
)
from ema_meeting_highlights import collect_latest_meeting_highlights
from scrape_data_fromMH_with_LLM import scrape_data_fromMH_with_LLM

COLUMNS = [
    'title', 'date', 'MH_url', 'epar_url', 'variation_url',
    'Product Name', 'INN', 'Initial Approval', 'Cancer', 'Orphan',
    'Therapy class', 'Therapy Area', 'Marketing authorisation holder',
    'Full Indication', 'New indication HTML', 'New indication PDF',
    'Removed indication HTML', 'CHMP Opinion Date', 'Decision date',
    'EMA date for extension', 'Search Result in NICE', 'NICE_url',
]


def build_ema_dataset(pdf_paths, therapy_area_df, df, pages=None):
    """Scrape the latest Meeting Highlights and return one row per medicine.

    Pass `pages` a dict to keep the trimmed markup of every page the run
    fetched, keyed by URL. `summarise.add_summaries` indexes those pages rather
    than downloading them again.
    """
    mh = collect_latest_meeting_highlights()
    print(f"Meeting Highlights: {mh['title']}")
    print(f"  {len(mh['epar_urls'])} EPAR URLs, {len(mh['variation_urls'])} variation URLs")

    indications = process_medicines_and_get_indications(mh['epar_urls'], pages)
    new_indications_html = process_medicines_and_new_indications_html(mh['variation_urls'], pages)
    removed_indications_html = process_medicines_and_removed_indications_html(
        mh['variation_urls'], pages)

    products = scrape_data_fromMH_with_LLM(
        mh, pdf_paths, therapy_area_df, df,
        indications, new_indications_html, removed_indications_html,
    )

    rows = [{
        'title': mh['title'],
        'date': mh['date'],
        'MH_url': mh['url'],
        'epar_url': p['epar_url'],
        'variation_url': ', '.join(p['variation_url']),
        'Product Name': p['Product Name'],
        'INN': p.get('INN', 'N/A'),
        'Initial Approval': p['Initial Approval'],
        'Cancer': p.get('Cancer', 'N/A'),
        'Orphan': p.get('Orphan medicine', 'N/A'),
        'Therapy class': p.get('Therapy class', 'N/A'),
        'Therapy Area': p.get('Therapy Area', 'N/A'),
        'Marketing authorisation holder': p.get('Marketing authorisation holder', 'N/A'),
        'Full Indication': p.get('Full indication', 'N/A'),
        'New indication HTML': p.get('New indication HTML', 'N/A'),
        'New indication PDF': p.get('New indication PDF', 'N/A'),
        'Removed indication HTML': p.get('Removed indication HTML', 'N/A'),
        'CHMP Opinion Date': mh['chmp_opinion_date'],
        'Decision date': p.get('European Commission decision date', 'N/A'),
        'EMA date for extension': p.get('Date for extension', 'N/A'),
        'Search Result in NICE': p.get('NICE', 'N/A'),
        'NICE_url': p.get('NICE_url', 'N/A'),
    } for p in products]

    return pd.DataFrame(rows, columns=COLUMNS)
