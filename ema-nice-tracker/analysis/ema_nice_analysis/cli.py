"""Command line for the analysis half of ema-nice-tracker.

    ema-nice-analysis enrich crawl.json -o dataset.xlsx
    ema-nice-analysis check  dataset.xlsx --crawl crawl.json
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from .checks import check_against_ema_tables, check_grounding, summarise
from .enrich import enrich, load_crawl, write
from .schema import REQUIRED
from .text import is_empty

DEFAULT_THERAPY_AREAS = Path(__file__).resolve().parents[2] / 'data' / 'therapy_area.xlsx'


def _read_dataset(path):
    """Read a dataset back without pandas turning the literal 'N/A' into NaN.

    That default silently made every column look 100% complete on re-read.
    """
    path = Path(path)
    if path.suffix.startswith('.xls'):
        return pd.read_excel(path, keep_default_na=False, na_values=[])
    return pd.read_csv(path, keep_default_na=False, na_values=[])


def _report_completeness(dataset):
    print(f'\n{len(dataset)} medicines')
    kinds = dataset['Initial Approval'].value_counts().to_dict()
    print('  ' + ', '.join(f'{count} {kind.lower()}' for kind, count in kinds.items()))

    print('\nHow complete is each column?')
    for column in ['Full Indication', 'New indication HTML', 'New indication PDF',
                   'Therapy Area', 'Decision date', 'Search Result in NICE']:
        if column in dataset.columns:
            filled = sum(not is_empty(value) for value in dataset[column])
            print(f'  {column:<26} {filled:>3}/{len(dataset)}')

    problems = []
    for column in REQUIRED:
        missing = [row['Product Name'] for _, row in dataset.iterrows()
                   if is_empty(row.get(column))]
        if missing:
            problems.append(f'{column} missing for {missing}')
    if problems:
        print('\nWARNING: these should never be empty - the page layout may have changed:')
        for problem in problems:
            print(f'  {problem}')
    return not problems


def cmd_enrich(args):
    crawl = load_crawl(args.crawl)
    print(f'Enriching {len(crawl["medicines"])} medicines from "{crawl["meeting"]["title"]}"')

    dataset = enrich(
        crawl,
        therapy_area_path=args.therapy_areas,
        pdf_dir=args.pdf_dir,
        cache_dir=args.cache_dir,
        with_summaries=args.summaries,
        skip_llm=args.skip_llm,
    )
    path = write(dataset, args.output)
    if args.preview:
        write(dataset, args.preview)
    _report_completeness(dataset)
    print(f'\nWrote {path}')
    return 0


def cmd_check(args):
    dataset = _read_dataset(args.dataset)
    ok = _report_completeness(dataset)

    if args.crawl:
        findings = check_grounding(dataset, load_crawl(args.crawl))
        print('\nGrounding - is every extracted phrase really on the page?')
        counts = summarise(findings, 'verdict')
        print('  ' + (', '.join(f'{v} {k}' for k, v in counts.items())
                      if counts else 'nothing extracted to check'))
        for finding in findings:
            if finding['verdict'] not in ('grounded',):
                print(f"  {finding['verdict']:<11} {finding['Product Name']:<22} "
                      f"{finding['field']}: {finding['detail']}")
                ok = False

    findings = check_against_ema_tables(dataset, args.cache_dir)
    print("\nAgreement with EMA's published tables")
    print('  ' + ', '.join(f'{v} {k}' for k, v in summarise(findings, 'result').items()))
    for finding in findings:
        if finding['result'] not in ('match', 'unchecked'):
            print(f"  {finding['result']:<11} {finding['Product Name']:<22} "
                  f"{finding['check']}: {finding['detail']}")
            ok = False

    print('\n' + ('All checks passed.' if ok else 'Some checks need a look - see above.'))
    return 0 if ok else 1


def build_parser():
    parser = argparse.ArgumentParser(prog='ema-nice-analysis', description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)

    enrich_cmd = subcommands.add_parser('enrich', help='turn a crawl into the dataset')
    enrich_cmd.add_argument('crawl', help='crawl.json produced by the crawler')
    enrich_cmd.add_argument('-o', '--output', default='dataset.xlsx',
                            help='.xlsx, .csv or .json (default: dataset.xlsx)')
    enrich_cmd.add_argument('--therapy-areas', default=str(DEFAULT_THERAPY_AREAS))
    enrich_cmd.add_argument('--pdf-dir', default=None,
                            help='folder of procedural steps PDFs, if you downloaded any')
    enrich_cmd.add_argument('--cache-dir', default='.cache',
                            help="where to keep EMA's downloaded reference tables")
    enrich_cmd.add_argument('--summaries', action='store_true',
                            help='add a plain-English "What changed" column')
    enrich_cmd.add_argument('--skip-llm', action='store_true',
                            help='scaffold the dataset without calling the model (no API key needed)')
    enrich_cmd.add_argument('--preview', default=None,
                            help='also write a JSON copy, for the web interface to render')
    enrich_cmd.set_defaults(func=cmd_enrich)

    check_cmd = subcommands.add_parser('check', help='run the label-free quality checks')
    check_cmd.add_argument('dataset')
    check_cmd.add_argument('--crawl', default=None,
                           help='crawl.json, to check extractions against their source pages')
    check_cmd.add_argument('--cache-dir', default='.cache')
    check_cmd.set_defaults(func=cmd_check)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
