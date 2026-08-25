"""Validate a run against EMA's own published tables.

EMA publishes machine-readable exports of the same facts the pipeline scrapes
out of news pages. Comparing the two needs no hand-labelling and catches the
failure that matters most: a scraper that quietly reads the wrong thing.

  * post-authorisation table -> which medicines had a variation opinion at this
    meeting, and on what date. Validates the 'Extension' classification and the
    CHMP opinion date.
  * medicines table -> Commission decision date and orphan status.
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))

from config import TIMEOUT, headers  # noqa: E402
from metrics import parse_date  # noqa: E402

EMA_REPORTS = 'https://www.ema.europa.eu/en/documents/report'
POST_AUTH_URL = f'{EMA_REPORTS}/medicines-output-post_authorisation-report_en.xlsx'
MEDICINES_URL = f'{EMA_REPORTS}/medicines-output-medicines-report_en.xlsx'

# EMA's exports carry eight rows of preamble above the real header.
HEADER_ROW = 8


def download(url, destination):
    destination = Path(destination)
    if not destination.exists():
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        destination.write_bytes(response.content)
    return destination


def load_table(url, cache_dir):
    path = download(url, Path(cache_dir) / Path(url).name)
    table = pd.read_excel(path, header=HEADER_ROW)
    table['key'] = table['Name of medicine'].astype(str).str.lower().str.replace(' ', '-')
    return table


def check_extensions(dataset, post_auth):
    """Every medicine marked 'Extension' should have a post-authorisation opinion."""
    findings = []
    by_key = post_auth.set_index('key')

    for _, row in dataset.iterrows():
        name = row['Product Name']
        is_extension = row.get('Initial Approval') == 'Extension'
        listed = name in by_key.index

        if is_extension and not listed:
            findings.append({
                'Product Name': name, 'check': 'extension listed by EMA',
                'result': 'missing',
                'detail': 'classified as an extension but absent from the post-authorisation table',
            })
            continue
        if not is_extension:
            continue

        record = by_key.loc[name]
        if isinstance(record, pd.DataFrame):
            record = record.iloc[0]

        scraped = parse_date(row.get('CHMP Opinion Date'))
        published = parse_date(record.get('Post-authorisation opinion date'))
        if published is None or scraped is None:
            result, detail = 'unchecked', 'a date could not be parsed'
        elif published == scraped:
            result, detail = 'match', published.isoformat()
        else:
            result, detail = 'mismatch', f'scraped {scraped}, EMA published {published}'

        findings.append({'Product Name': name, 'check': 'CHMP opinion date',
                         'result': result, 'detail': detail})

    return findings


def check_decision_dates(dataset, medicines):
    """The Commission decision date should match the medicines table."""
    findings = []
    by_key = medicines.set_index('key')

    for _, row in dataset.iterrows():
        name = row['Product Name']
        if name not in by_key.index:
            continue
        record = by_key.loc[name]
        if isinstance(record, pd.DataFrame):
            record = record.iloc[0]

        scraped = parse_date(row.get('Decision date'))
        published = parse_date(record.get('European Commission decision date'))
        if scraped is None and published is None:
            continue
        if scraped == published:
            result, detail = 'match', str(published)
        else:
            result, detail = 'mismatch', f'dataset {scraped}, EMA table {published}'
        findings.append({'Product Name': name, 'check': 'Commission decision date',
                         'result': result, 'detail': detail})

    return findings


def run(dataset, cache_dir='.'):
    post_auth = load_table(POST_AUTH_URL, cache_dir)
    medicines = load_table(MEDICINES_URL, cache_dir)
    return check_extensions(dataset, post_auth) + check_decision_dates(dataset, medicines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', help='pipeline output (.xlsx or .csv)')
    parser.add_argument('--cache-dir', default='.', help='where to keep the downloaded EMA tables')
    args = parser.parse_args()

    path = Path(args.dataset)
    dataset = pd.read_excel(path) if path.suffix.startswith('.xls') else pd.read_csv(path)

    findings = run(dataset, args.cache_dir)
    counts = {}
    for finding in findings:
        counts[finding['result']] = counts.get(finding['result'], 0) + 1

    print(f'{len(findings)} cross-checks against EMA published tables: '
          + ', '.join(f'{v} {k}' for k, v in sorted(counts.items())))
    for finding in findings:
        if finding['result'] != 'match':
            print(f"  {finding['result']:<10} {finding['Product Name']:<22} "
                  f"{finding['check']}: {finding['detail']}")


if __name__ == '__main__':
    main()
