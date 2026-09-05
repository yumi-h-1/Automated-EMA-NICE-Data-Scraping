"""Downloading the EMA procedural steps PDF for a medicine.

`New indication PDF` and `EMA date for extension` are read out of EMA's
"Procedural steps taken and scientific information after authorisation"
document. That file used to be downloaded by hand, which was the one step in
the pipeline the notebook could not do for itself.

It does not need to be. The EPAR page links the PDF under a fixed path
segment, so it can be found the same way everything else here is found. The
anchor text is only 'View', so the href is the only thing worth matching on.

Only authorised medicines have one. A medicine that has just received a
positive opinion has no post-authorisation history yet, so there is nothing to
download and both columns stay 'N/A' — which is the same condition that already
decides whether the PDF prompts run at all.
"""

from pathlib import Path

import requests

from config import TIMEOUT, headers
from ema_meeting_highlights import absolute
from http_utils import fetch_soup

_PROCEDURAL_STEPS = '/documents/procedural-steps-after/'

# EMA publishes two of these. The '-archive' file holds the older history; the
# current one ends with the change this meeting made, which is what the prompts
# ask for.
_ARCHIVE = '-archive'


def procedural_pdf_url(epar_url, soup=None):
    """URL of a medicine's current procedural steps PDF, or None if it has none."""
    soup = fetch_soup(epar_url) if soup is None else soup
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if _PROCEDURAL_STEPS in href and _ARCHIVE not in href and href.endswith('_en.pdf'):
            return absolute(href)
    return None


def download_procedural_pdf(epar_url, directory, soup=None):
    """Download a medicine's procedural steps PDF and return its path, or None.

    A file already in `directory` is reused rather than downloaded again, so
    re-running the notebook does not re-fetch every PDF.
    """
    url = procedural_pdf_url(epar_url, soup)
    if url is None:
        return None

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / url.rsplit('/', 1)[-1]
    if destination.exists():
        return str(destination)

    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    # A redirect to an error page returns 200 and HTML; pypdf would then fail
    # further downstream, where the cause is much harder to see.
    if not response.content.startswith(b'%PDF'):
        raise RuntimeError(f'{url} did not return a PDF')

    destination.write_bytes(response.content)
    return str(destination)
