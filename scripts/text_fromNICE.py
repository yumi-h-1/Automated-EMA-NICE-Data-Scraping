"""Plain text of each NICE search-result page, keyed by URL."""

from http_utils import fetch_soup, page_text


def text_fromNICE(Nice_url_list):
    nice_text_dict = {}

    for NICE_url in dict.fromkeys(Nice_url_list):  # de-duplicate, keep order
        try:
            nice_text_dict[NICE_url] = page_text(fetch_soup(NICE_url))
        except Exception as e:
            print(f'Error processing {NICE_url}: {e}')
            nice_text_dict[NICE_url] = 'Error fetching or processing the page'

    return nice_text_dict
