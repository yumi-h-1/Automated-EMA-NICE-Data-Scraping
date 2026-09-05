#!/usr/bin/env python3
"""Run the whole pipeline from the terminal, without Jupyter.

Does exactly what notebooks/EMA_data_scraping.ipynb does, in the same order,
by calling the same functions — the notebook is for reading the result, this is
for reproducing it.

    python run_pipeline.py                     # full run into results/
    python run_pipeline.py --no-summaries      # skip retrieval (no heavy deps needed)
    python run_pipeline.py --output-dir /tmp/x # write somewhere else
    python run_pipeline.py --no-refresh        # keep the cached EMA medicines table

Needs OPENAI_API_KEY. Put it in .env in the project root; config.py loads it.
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'evaluation'))

import pandas as pd

EMA_MEDICINES_URL = ('https://www.ema.europa.eu/en/documents/report/'
                     'medicines-output-medicines-report_en.xlsx')

# Columns that should never be empty. Anything here means a scraper is broken,
# not that the medicine happens to have no value.
REQUIRED = ['Product Name', 'INN', 'Marketing authorisation holder', 'Full Indication']

REPORT_ON = ['Full Indication', 'New indication HTML', 'Removed indication HTML',
             'New indication PDF', 'EMA date for extension', 'Therapy Area',
             'Decision date', 'Search Result in NICE']


def refresh_medicines_table(path):
    """Always re-download: the table changes weekly, and a stale copy produces
    out-of-date Commission decision dates rather than an error."""
    import requests
    from config import headers

    response = requests.get(EMA_MEDICINES_URL, headers=headers, timeout=(10, 180))
    response.raise_for_status()
    path.write_bytes(response.content)


def main():
    parser = argparse.ArgumentParser(
        description='Scrape the latest CHMP meeting into a structured dataset.')
    parser.add_argument('--output-dir', default=ROOT / 'results', type=Path,
                        help='where to write EMA_data.csv and final_EMA_dataset.xlsx')
    parser.add_argument('--data-dir', default=ROOT / 'data', type=Path,
                        help='holds the EMA medicines table and therapy_area.xlsx')
    parser.add_argument('--pdf-dir', default=None, type=Path,
                        help='procedural steps PDFs; missing ones are downloaded here '
                             '(default: <data-dir>/ema_pdf)')
    parser.add_argument('--no-summaries', action='store_true',
                        help='skip the retrieval step, so langchain/chromadb are not needed')
    parser.add_argument('--no-refresh', action='store_true',
                        help='use the cached EMA medicines table instead of downloading it')
    args = parser.parse_args()

    started = time.time()
    stamp = lambda: f'[{time.time() - started:5.0f}s]'

    from build_dataset import build_ema_dataset
    from compare_nice_and_indication import compare_nice_and_indication
    from text_fromNICE import text_fromNICE

    medicines_xlsx = args.data_dir / 'medicines_output_medicines_en.xlsx'
    pdf_dir = args.pdf_dir or (args.data_dir / 'ema_pdf')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if args.no_refresh:
        print(f'{stamp()} using the cached EMA medicines table')
    else:
        try:
            refresh_medicines_table(medicines_xlsx)
            print(f'{stamp()} downloaded the current EMA medicines table')
        except Exception as e:
            print(f'{stamp()} could not refresh the EMA table ({e}); using the existing copy')

    # The real header row of the EMA export sits on row 9 of the sheet.
    medicines = pd.read_excel(medicines_xlsx, header=8)
    medicines['Name of medicine'] = (
        medicines['Name of medicine'].str.lower().str.replace(' ', '-'))
    therapy_areas = pd.read_excel(args.data_dir / 'therapy_area.xlsx')
    print(f'{stamp()} {len(medicines)} medicines, {len(therapy_areas)} therapy areas')

    pdf_paths = [str(p) for p in pdf_dir.glob('*.pdf')]
    print(f'{stamp()} {len(pdf_paths)} procedural steps PDFs already local')

    # `pages` keeps the trimmed markup of every page fetched, so the retrieval
    # step below indexes exactly these rather than downloading them again.
    pages = {}
    dataset = build_ema_dataset(pdf_paths, therapy_areas, medicines,
                                pages=pages, pdf_dir=str(pdf_dir))
    dataset.to_csv(args.output_dir / 'EMA_data.csv', index=False)
    print(f'{stamp()} built {dataset.shape}, {len(pages)} pages kept for retrieval')

    nice_urls = [u for u in dataset['NICE_url'].dropna().unique() if u != 'N/A']
    nice_texts = text_fromNICE(nice_urls)
    print(f'{stamp()} {len(nice_texts)} NICE pages fetched')

    for output_column, indication_column in {
            'Full Indication Similarity': 'Full Indication',
            'New Indication HTML Similarity': 'New indication HTML',
            'New Indication PDF Similarity': 'New indication PDF'}.items():
        results = compare_nice_and_indication(
            nice_texts, dataset[[indication_column, 'NICE_url']])
        lookup = {r['NICE_url']: r['Result'] for r in results}
        dataset[output_column] = dataset['NICE_url'].map(lookup).fillna('N/A')
    print(f'{stamp()} similarity columns added {dataset.shape}')

    if args.no_summaries:
        print(f'{stamp()} skipping summaries (--no-summaries)')
    else:
        from summarise import add_summaries
        retrieval_log = {}
        add_summaries(dataset, pages, nice_texts, retrieval_log=retrieval_log)
        print(f'{stamp()} summaries added {dataset.shape}')

        from grounding import check_retrieval, check_summaries, mean_recall
        retrieval = check_retrieval(dataset, retrieval_log, pages)
        recall = mean_recall(retrieval)
        print(f'{stamp()} retrieval recall: '
              + ('no marked-up change at this meeting' if recall is None
                 else f'{recall:.2f} over {len(retrieval)} medicines'))
        verdicts = {}
        for finding in check_summaries(dataset, retrieval_log):
            verdicts[finding['verdict']] = verdicts.get(finding['verdict'], 0) + 1
        print(f'{stamp()} summary verdicts: {verdicts}')

    excel = args.output_dir / 'final_EMA_dataset.xlsx'
    dataset.to_excel(excel, index=False)

    total = len(dataset)
    print(f'\n{total} medicines from: {dataset["title"].iloc[0]}')
    print(f'  {(dataset["Initial Approval"] == "Initial approval").sum()} new medicines, '
          f'{(dataset["Initial Approval"] == "Extension").sum()} extensions of indication')
    print('\nHow complete is each column?')
    for column in REPORT_ON:
        if column in dataset:
            filled = (dataset[column].astype(str) != 'N/A').sum()
            print(f'  {column:<26} {filled:>3}/{total}')

    broken = False
    for column in REQUIRED:
        missing = dataset.loc[dataset[column].astype(str) == 'N/A', 'Product Name'].tolist()
        if missing:
            broken = True
            print(f'\nWARNING: {column} is missing for {missing} — check the EMA page layout')

    print(f'\nSaved {excel} ({dataset.shape[0]} rows, {dataset.shape[1]} columns)')
    return 1 if broken else 0


if __name__ == '__main__':
    sys.exit(main())
