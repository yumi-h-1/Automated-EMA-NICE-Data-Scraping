"""Fetch a list of pages and run one extractor over each.

Replaces the three former process_medicines_and_*.py modules, which differed
only in which prompt they called.
"""

from extractors import (
    query_model_for_indication,
    query_model_for_new_indication_html,
    query_model_for_removed_indication_html,
)
from http_utils import condense_html, epar_indication_html, fetch_soup


def _run(urls, trim, extract, label):
    results = {}
    for url in dict.fromkeys(urls):  # de-duplicate, keep order
        try:
            results[url] = extract(trim(fetch_soup(url)))
        except Exception as e:
            print(f'Error processing {url}: {e}')
            results[url] = 'Error fetching or processing the page'
        print(f'  {label}: {url}')
    return results


def process_medicines_and_get_indications(epar_urls):
    """{epar_url: full indication} for every EPAR page."""
    return _run(epar_urls, epar_indication_html, query_model_for_indication, 'indication')


def process_medicines_and_new_indications_html(variation_urls):
    """{variation_url: newly added indication} from bold text."""
    return _run(variation_urls, condense_html, query_model_for_new_indication_html, 'new indication')


def process_medicines_and_removed_indications_html(variation_urls):
    """{variation_url: removed indication} from strikethrough text."""
    return _run(variation_urls, condense_html, query_model_for_removed_indication_html, 'removed indication')
