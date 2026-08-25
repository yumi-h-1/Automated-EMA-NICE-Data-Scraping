"""Score a pipeline run against a hand-checked gold file.

    python evaluation/evaluate.py results/final_EMA_dataset.xlsx evaluation/gold.csv

Both files are keyed on 'Product Name'. Only the rows present in the gold file
are scored, so you can annotate a sample rather than every medicine.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from metrics import binary_report, date_report, span_report

# Which metric applies to which column.
SPAN_FIELDS = [
    'Full Indication',
    'New indication HTML',
    'New indication PDF',
    'Removed indication HTML',
]
DATE_FIELDS = ['EMA date for extension']
BINARY_FIELDS = [
    'Search Result in NICE',
    'Full Indication Similarity',
    'New Indication HTML Similarity',
    'New Indication PDF Similarity',
]

KEY = 'Product Name'


def load(path):
    path = Path(path)
    frame = pd.read_excel(path) if path.suffix in ('.xlsx', '.xls') else pd.read_csv(path)
    return frame.set_index(KEY)


def format_report(name, report):
    if not report or report.get('n', 0) == 0:
        return f'  {name:<34} (no gold labels)'
    numbers = '  '.join(f'{k}={v:.3f}' for k, v in report.items() if k != 'n')
    return f'  {name:<34} n={report["n"]:<4} {numbers}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('predictions', help='pipeline output (.xlsx or .csv)')
    parser.add_argument('gold', help='hand-checked reference file (.csv)')
    args = parser.parse_args()

    predictions, gold = load(args.predictions), load(args.gold)
    shared = gold.index.intersection(predictions.index)
    if shared.empty:
        raise SystemExit(f'No medicines in common between the two files (key: {KEY}).')

    missing = gold.index.difference(predictions.index)
    print(f'Scoring {len(shared)} medicines'
          + (f' ({len(missing)} in the gold file were not produced: {list(missing)})' if len(missing) else ''))

    pred, ref = predictions.loc[shared], gold.loc[shared]

    print('\nVerbatim extraction — exact_match is the headline; ROUGE shows how near the misses were')
    for field in SPAN_FIELDS:
        if field in ref.columns and field in pred.columns:
            print(format_report(field, span_report(pred[field], ref[field])))

    print('\nDates — exact match only')
    for field in DATE_FIELDS:
        if field in ref.columns and field in pred.columns:
            print(format_report(field, date_report(pred[field], ref[field])))

    print('\nYes/no judgements — classification metrics')
    for field in BINARY_FIELDS:
        if field in ref.columns and field in pred.columns:
            print(format_report(field, binary_report(pred[field], ref[field])))


if __name__ == '__main__':
    main()
