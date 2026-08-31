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


def _run(urls, trim, extract, label, pages=None):
    """Extract from every URL in turn.

    `pages` collects the trimmed markup as {url: html} when a dict is passed.
    The retrieval step behind the summaries indexes exactly these pages, and
    fetching them a second time would double the load on EMA for no reason.
    """
    results = {}
    for url in dict.fromkeys(urls):  # de-duplicate, keep order
        try:
            trimmed = trim(fetch_soup(url))
            if pages is not None:
                pages[url] = trimmed
            results[url] = extract(trimmed)
        except Exception as e:
            print(f'Error processing {url}: {e}')
            results[url] = 'Error fetching or processing the page'
        print(f'  {label}: {url}')
    return results


def process_medicines_and_get_indications(epar_urls, pages=None):
    """{epar_url: full indication} for every EPAR page."""
    return _run(epar_urls, epar_indication_html, query_model_for_indication,
                'indication', pages)


def process_medicines_and_new_indications_html(variation_urls, pages=None):
    """{variation_url: newly added indication} from bold text."""
    return _run(variation_urls, condense_html, query_model_for_new_indication_html,
                'new indication', pages)


def process_medicines_and_removed_indications_html(variation_urls, pages=None):
    """{variation_url: removed indication} from strikethrough text."""
    return _run(variation_urls, condense_html, query_model_for_removed_indication_html,
                'removed indication', pages)
