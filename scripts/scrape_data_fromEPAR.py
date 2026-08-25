"""Therapy class, cancer flag and therapy area, from an EPAR page."""

import re

from http_utils import fetch_soup
from scrape_data_fromSHEET import scrape_data_fromSHEET
from scrape_therapy_area import scrape_therapy_area

_ATC_LABEL = re.compile(r'Anatomical therapeutic chemical \(ATC\) code')
_GROUP_COLUMN = 'Pharmacotherapeutic group\n(human)'


def scrape_data_fromEPAR(epar_url, product_data, therapy_area_df, df):
    therapy_class = 'N/A'
    try:
        epar_soup = fetch_soup(epar_url)
        atc_code_tag = epar_soup.find('dt', string=_ATC_LABEL)
        if atc_code_tag:
            # ATC codes are hierarchical; the first three characters are the
            # therapeutic subgroup used for the therapy-area lookup.
            therapy_class = atc_code_tag.find_next('dd').get_text(strip=True)[:3]
        else:
            # Medicines with only a CHMP opinion have no ATC code on the page yet.
            sheet_data = scrape_data_fromSHEET(product_data['Product Name'], df, [_GROUP_COLUMN])
            if sheet_data and sheet_data.get(_GROUP_COLUMN):
                therapy_class = sheet_data[_GROUP_COLUMN]
    except Exception as e:
        print(f'Error extracting ATC code or Therapy class for {epar_url}: {e}')

    product_data['Therapy class'] = therapy_class
    product_data['Cancer'] = 'Yes' if therapy_class in ('L01', 'L02') else 'No'
    product_data['Therapy Area'] = scrape_therapy_area(therapy_class, therapy_area_df, 'Therapy Area') or 'N/A'

    return product_data
