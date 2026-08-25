"""Turn a crawl into the published dataset.

The crawler has already done every network fetch and trimmed each page down to
the part that matters, so this stage is pure enrichment: run the prompts, join
EMA's reference tables, and shape the result into the documented columns.
"""

import json
from pathlib import Path

import pandas as pd

from . import prompts
from .lookup import medicines_table, row_for, therapy_areas
from .pdf import indication_and_date_from_pdfs
from .schema import COLUMNS, MISSING

#: ATC subgroups that mark a medicine as oncology.
CANCER_CLASSES = {'L01', 'L02'}

GROUP_COLUMN = 'Pharmacotherapeutic group\n(human)'


def load_crawl(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _value(row, column):
    """A cell from an EMA table row, normalised to a string or 'N/A'."""
    if row is None or column not in row.index:
        return MISSING
    value = row[column]
    if pd.isna(value):
        return MISSING
    return str(value).strip()


def _therapy_class(medicine, sheet_row):
    """The ATC therapeutic subgroup, falling back to EMA's medicines table.

    Medicines that only have a positive opinion carry no ATC code on their EPAR
    page until the Commission decides.
    """
    if medicine.get('therapyClass'):
        return medicine['therapyClass']
    fallback = _value(sheet_row, GROUP_COLUMN)
    return fallback if fallback != MISSING else MISSING


def enrich(crawl, therapy_area_path, pdf_dir=None, cache_dir='.',
           with_summaries=False, skip_llm=False):
    """Build the dataset. Returns a DataFrame with the documented columns."""
    medicines_lookup = medicines_table(cache_dir)
    areas = therapy_areas(therapy_area_path)
    area_by_class = dict(zip(areas['Therapy Class'], areas['Therapy Area']))

    meeting = crawl['meeting']
    rows = []

    for medicine in crawl['medicines']:
        name = medicine['productName']
        sheet_row = row_for(medicines_lookup, medicine['slug'])

        therapy_class = _therapy_class(medicine, sheet_row)
        variation_html = medicine.get('variationHtml') or {}
        is_extension = medicine['recommendation'] == 'Extension'

        if skip_llm:
            full_indication = new_indication = removed_indication = MISSING
        else:
            full_indication = (
                prompts.full_indication(medicine['indicationHtml'])
                if medicine.get('indicationHtml') else MISSING
            )
            new_indication = ', '.join(
                prompts.new_indication(html) for html in variation_html.values()
            ) or MISSING
            removed_indication = ', '.join(
                prompts.removed_indication(html) for html in variation_html.values()
            ) or MISSING

        pdf_indication, pdf_date = MISSING, MISSING
        if is_extension and pdf_dir and not skip_llm:
            pdf_indication, pdf_date = indication_and_date_from_pdfs(medicine['slug'], pdf_dir)

        similarity = {column: MISSING for column in (
            'Full Indication Similarity',
            'New Indication HTML Similarity',
            'New Indication PDF Similarity',
        )}
        if medicine.get('niceText') and not skip_llm:
            for column, indication in (
                ('Full Indication Similarity', full_indication),
                ('New Indication HTML Similarity', new_indication),
                ('New Indication PDF Similarity', pdf_indication),
            ):
                if indication and indication != MISSING:
                    similarity[column] = prompts.nice_similarity(medicine['niceText'], indication)

        row = {
            'Product Name': name,
            'INN': medicine.get('inn') or MISSING,
            'Marketing authorisation holder': medicine.get('marketingAuthorisationHolder') or MISSING,
            'epar_url': medicine['eparUrl'],
            'variation_url': ', '.join(medicine.get('variationUrls', [])) or MISSING,
            'MH_url': meeting['url'],

            'Full Indication': full_indication,
            'New indication HTML': new_indication,
            'Removed indication HTML': removed_indication,
            'New indication PDF': pdf_indication,
            'Therapy class': therapy_class,
            'Therapy Area': area_by_class.get(therapy_class, MISSING),
            'Cancer': 'Yes' if therapy_class in CANCER_CLASSES else 'No',
            'Orphan': _value(sheet_row, 'Orphan medicine'),

            'Initial Approval': medicine['recommendation'],
            'CHMP Opinion Date': meeting.get('chmpOpinionDate') or MISSING,
            'Decision date': _value(sheet_row, 'European Commission decision date'),
            'EMA date for extension': pdf_date,
            'title': meeting['title'],
            'date': meeting.get('published') or MISSING,

            'Search Result in NICE': (
                MISSING if medicine.get('niceHasResults') is None
                else ('Yes' if medicine['niceHasResults'] else 'No')
            ),
            'NICE_url': medicine.get('niceUrl') or MISSING,
            **similarity,
        }

        if with_summaries and not skip_llm:
            row['What changed'] = prompts.change_summary(
                name, medicine['recommendation'], full_indication,
                medicine.get('markedUpAdded', []), medicine.get('markedUpRemoved', []),
            )

        rows.append(row)

    columns = COLUMNS + (['What changed'] if with_summaries and not skip_llm else [])
    return pd.DataFrame(rows, columns=columns)


def write(dataset, output):
    """Write the dataset out; the extension picks the format."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix in ('.xlsx', '.xls'):
        dataset.to_excel(path, index=False)
    elif path.suffix == '.json':
        path.write_text(dataset.to_json(orient='records', indent=2), encoding='utf-8')
    else:
        dataset.to_csv(path, index=False)

    return path
