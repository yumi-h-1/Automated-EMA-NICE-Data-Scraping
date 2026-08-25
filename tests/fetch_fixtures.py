"""Re-download the saved pages the regression tests run against.

The pipeline breaks when EMA or NICE change their markup, not when the model has
a bad day. These fixtures pin the structure the scrapers depend on, so a site
redesign shows up as a failing test instead of an empty output file.

    python tests/fetch_fixtures.py            # refresh every fixture
    python tests/fetch_fixtures.py meeting    # refresh the ones matching 'meeting'

Fixtures are gzipped because a full EPAR page is ~460 kB of HTML.
"""

import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import requests

from config import TIMEOUT, headers

FIXTURE_DIR = Path(__file__).parent / 'fixtures'

EMA = 'https://www.ema.europa.eu'
NICE = 'https://www.nice.org.uk'

FIXTURES = {
    # Listing page: the CHMP Meeting Highlights link pattern lives here.
    'ema_news': f'{EMA}/en/news?f%5B0%5D=ema_news_responsible_body%3A100002',
    # A Meeting Highlights item: section headings, product names, INN/holder
    # definition lists, and variation links.
    'meeting_highlights': f'{EMA}/en/news/meeting-highlights-committee-medicinal-products-human-use-chmp-20-23-july-2026',
    # A large authorised medicine: has an ATC code and a Therapeutic indication
    # subsection, and is big enough to prove the page-trimming works.
    'epar_keytruda': f'{EMA}/en/medicines/human/EPAR/keytruda',
    # A medicine with only a positive opinion: no ATC code, Overview only.
    'epar_evlarco': f'{EMA}/en/medicines/human/EPAR/evlarco',
    # Variation pages: bold = added indication, strikethrough = removed.
    'variation_enhertu': f'{EMA}/en/medicines/human/variation/enhertu',
    'variation_jivi': f'{EMA}/en/medicines/human/variation/jivi',
    'variation_repatha': f'{EMA}/en/medicines/human/variation/repatha',
    # NICE search, with and without hits.
    'nice_pembrolizumab': f'{NICE}/search?q=pembrolizumab',
    'nice_no_results': f'{NICE}/search?q=zzzznotadrugxyz',
}


def path_for(name):
    return FIXTURE_DIR / f'{name}.html.gz'


def load(name):
    """Return the saved HTML for a fixture."""
    with gzip.open(path_for(name), 'rt', encoding='utf-8') as f:
        return f.read()


def fetch(name, url):
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = 'utf-8'
    with gzip.open(path_for(name), 'wt', encoding='utf-8') as f:
        f.write(response.text)
    return len(response.text)


def main():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:]
    for name, url in FIXTURES.items():
        if wanted and not any(w in name for w in wanted):
            continue
        try:
            size = fetch(name, url)
            print(f'  {name:<22} {size:>8,} chars  {url}')
        except Exception as e:
            print(f'  {name:<22} FAILED: {e}')


if __name__ == '__main__':
    main()
