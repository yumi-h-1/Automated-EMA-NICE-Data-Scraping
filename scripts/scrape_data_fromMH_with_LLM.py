"""Assemble one record per medicine from a CHMP Meeting Highlights news item."""

import re

from ema_meeting_highlights import find_section_heading, section_kind, absolute, BASE_URL
from extract_text_from_pdf import extract_text_from_pdf
from extractors import query_model_for_ema_date, query_model_for_new_indication_pdf
from scrape_data_fromEPAR import scrape_data_fromEPAR
from scrape_data_fromNICE import scrape_data_fromNICE
from scrape_data_fromSHEET import scrape_data_fromSHEET

_INN_LABEL = re.compile(r'International non-proprietary name \(INN\)|^INN$')
_COMMON_NAME_LABEL = re.compile(r'Common name')
_APPLICANT_LABEL = re.compile(r'Marketing[- ]authorisation applicant', re.IGNORECASE)
_HOLDER_LABEL = re.compile(r'Marketing[- ]authorisation holder', re.IGNORECASE)


def _definition(item, label_pattern):
    """Value of a <dt>/<dd> pair whose label matches `label_pattern`."""
    tag = item.find('dt', string=label_pattern)
    return tag.find_next('dd').get_text(strip=True) if tag else None


def scrape_data_fromMH_with_LLM(mh, pdf_paths, therapy_area_df, df, indications,
                                new_indications_html, removed_indications_html):
    """Build the per-medicine records for one Meeting Highlights page.

    `mh` is the dict returned by collect_latest_meeting_highlights(); the other
    arguments are the lookup tables and the pre-computed LLM extractions.
    """
    product_data_list = []
    initial_approval = None

    for item in mh['soup'].find_all('div', class_='item'):
        try:
            heading = find_section_heading(item)
            if heading:
                initial_approval = section_kind(heading.get_text(strip=True))
                continue

            # Outside a positively-recommended section (negative opinions,
            # withdrawals, generics, biosimilars, statistics).
            if initial_approval is None:
                continue

            product_name_tag = item.find('h3', class_='mb-4')
            if not product_name_tag:
                continue
            product_name = product_name_tag.get_text(strip=True).lower().replace(' ', '-')

            epar_url = f'{BASE_URL}/en/medicines/human/EPAR/{product_name}'

            variation_urls = [
                absolute(a['href']) for a in item.find_all('a', href=True)
                if '/en/medicines/human/variation/' in a['href']
            ]
            if not variation_urls:
                variation_urls = [f'{BASE_URL}/en/medicines/human/variation/{product_name}']

            product_data = {
                'Product Name': product_name,
                'Recommendation': 'Positive',
                'Initial Approval': initial_approval,
                'Date for extension': 'N/A',
                'Full indication': indications.get(epar_url, 'N/A'),
                'New indication PDF': 'N/A',
                'epar_url': epar_url,
                'variation_url': variation_urls,
            }

            product_data['New indication HTML'] = ', '.join(
                new_indications_html.get(url, 'N/A') for url in variation_urls
            )
            product_data['Removed indication HTML'] = ', '.join(
                removed_indications_html.get(url, 'N/A') for url in variation_urls
            )

            try:
                product_data = scrape_data_fromEPAR(epar_url, product_data, therapy_area_df, df)
            except Exception as e:
                print(f'Error scraping data from EPAR for {product_name}: {e}')

            inn = _definition(item, _INN_LABEL) or _definition(item, _COMMON_NAME_LABEL)
            product_data['INN'] = inn or 'N/A'
            if inn:
                nice_url = f'https://www.nice.org.uk/search?q={inn}'
                product_data['NICE_url'] = nice_url
                try:
                    product_data = scrape_data_fromNICE(nice_url, product_data)
                except Exception as e:
                    print(f'Error scraping data from NICE for {inn}: {e}')

            product_data['Marketing authorisation holder'] = (
                _definition(item, _APPLICANT_LABEL)
                or _definition(item, _HOLDER_LABEL)
                or 'N/A'
            )

            try:
                sheet_data = scrape_data_fromSHEET(
                    product_name, df, ['Orphan medicine', 'European Commission decision date']
                )
                if sheet_data:
                    product_data.update(sheet_data)
            except Exception as e:
                print(f'Error matching data from sheet for {product_name}: {e}')

            matching_pdf = next((pdf for pdf in pdf_paths if product_name in pdf.lower()), None)
            if matching_pdf and initial_approval == 'Extension':
                print(f'Processing PDF: {matching_pdf} for product: {product_name}')
                try:
                    pdf_text = extract_text_from_pdf(matching_pdf)
                    product_data['Date for extension'] = query_model_for_ema_date(pdf_text)
                    product_data['New indication PDF'] = query_model_for_new_indication_pdf(pdf_text)
                except Exception as e:
                    print(f'Error processing PDF {matching_pdf} for {product_name}: {e}')

            product_data_list.append(product_data)

        except Exception as e:
            print(f'Error processing item: {e}')

    return product_data_list
