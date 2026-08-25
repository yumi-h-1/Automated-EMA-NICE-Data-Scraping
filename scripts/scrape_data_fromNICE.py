"""Whether a medicine appears in NICE search results."""

import re

from http_utils import fetch_soup


def scrape_data_fromNICE(nice_url, product_data):
    try:
        title_tag = fetch_soup(nice_url).find('title')
        title_text = title_tag.get_text(strip=True) if title_tag else ''
    except Exception as e:
        print(f'Error extracting title from NICE page: {nice_url}. Error: {e}')
        product_data['NICE'] = 'N/A'
        return product_data

    # NICE titles read '<query> | Search results | NICE', or
    # 'No results | Search results | NICE' when nothing matched.
    if 'No results' in title_text:
        product_data['NICE'] = 'N/A'
    else:
        try:
            searched_name = title_text.split('|')[0].strip()
            matched = re.search(re.escape(product_data['INN']), searched_name, re.IGNORECASE)
            product_data['NICE'] = 'Yes' if matched else 'No'
        except Exception as e:
            print(f'Error processing INN matching for NICE page: {nice_url}. Error: {e}')
            product_data['NICE'] = 'N/A'

    return product_data
