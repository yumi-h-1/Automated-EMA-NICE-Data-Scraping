"""EMA's published reference tables.

These are downloaded rather than bundled. A stale copy does not raise an error,
it silently produces years-old Commission decision dates, which is harder to
notice than a failed download.
"""

import time
from pathlib import Path

import pandas as pd
import requests

EMA_REPORTS = 'https://www.ema.europa.eu/en/documents/report'
MEDICINES_URL = f'{EMA_REPORTS}/medicines-output-medicines-report_en.xlsx'
POST_AUTHORISATION_URL = f'{EMA_REPORTS}/medicines-output-post_authorisation-report_en.xlsx'

#: EMA's exports carry eight rows of preamble above the real header.
HEADER_ROW = 8

#: Re-download anything older than this.
MAX_AGE_SECONDS = 12 * 60 * 60

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def download(url, cache_dir, max_age=MAX_AGE_SECONDS):
    """Fetch an EMA export, reusing a recent local copy if there is one."""
    destination = Path(cache_dir) / Path(url).name
    destination.parent.mkdir(parents=True, exist_ok=True)

    fresh = destination.exists() and (time.time() - destination.stat().st_mtime) < max_age
    if not fresh:
        try:
            response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=(10, 120))
            response.raise_for_status()
            destination.write_bytes(response.content)
        except Exception as e:
            if not destination.exists():
                raise
            print(f'Could not refresh {destination.name} ({e}); using the cached copy')

    return destination


def _keyed(table):
    """Add the lower-cased, hyphenated key EMA uses in its URLs."""
    table = table.copy()
    table['key'] = table['Name of medicine'].astype(str).str.lower().str.replace(' ', '-')
    return table


def medicines_table(cache_dir='.'):
    """EMA's list of every medicine, with decision dates and orphan status."""
    return _keyed(pd.read_excel(download(MEDICINES_URL, cache_dir), header=HEADER_ROW))


def post_authorisation_table(cache_dir='.'):
    """Variation procedures currently in progress, with their opinion dates."""
    return _keyed(pd.read_excel(download(POST_AUTHORISATION_URL, cache_dir), header=HEADER_ROW))


def therapy_areas(path):
    """The ATC-subgroup-to-therapy-area mapping shipped with this repository."""
    return pd.read_excel(path)


def row_for(table, key):
    """One row from a keyed table, or None."""
    matches = table.loc[table['key'] == key]
    return None if matches.empty else matches.iloc[0]
