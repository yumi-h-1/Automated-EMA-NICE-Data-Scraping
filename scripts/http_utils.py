"""Fetching and trimming HTML.

EMA pages carry a lot of navigation, scripts and document tables that are
irrelevant to indication extraction. A Keytruda EPAR page is ~200k tokens when
sent verbatim, which no longer fits in the model's context window, so pages are
narrowed to the relevant section before they reach the model.
"""

import random
import re
import time

import requests
from bs4 import BeautifulSoup

from config import TIMEOUT, headers

# Tags that never carry content we care about.
_NOISE_TAGS = [
    'script', 'style', 'noscript', 'svg', 'head', 'nav', 'footer',
    'form', 'iframe', 'link', 'meta', 'button', 'picture', 'source',
]


def fetch_soup(url, attempts=3):
    """GET a URL and return a BeautifulSoup document, retrying transient errors."""
    last_error = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(2 ** attempt + random.random())
    raise RuntimeError(f'Could not fetch {url}: {last_error}')


def condense_html(soup):
    """Strip noise and attributes, keeping the markup the prompts rely on.

    <strong> (newly added indications) and <s> (removed indications) survive,
    because the extraction prompts key off exactly those tags.
    """
    doc = BeautifulSoup(str(soup), 'html.parser')
    for tag in doc(_NOISE_TAGS):
        tag.decompose()

    root = doc.find('main') or doc.find(attrs={'role': 'main'}) or doc.body or doc
    for tag in root.find_all(True):
        tag.attrs = {}

    return re.sub(r'\n\s*\n+', '\n', root.prettify())


def _section_for_heading(soup, pattern):
    """Return the smallest section container whose heading matches `pattern`."""
    for heading in soup.find_all(['h2', 'h3']):
        if not re.search(pattern, heading.get_text(strip=True), re.IGNORECASE):
            continue
        node = heading
        for _ in range(4):
            node = node.parent
            if node is None:
                break
            classes = node.get('class') or []
            if 'subsection' in classes or 'section' in classes:
                return node
        return heading.parent
    return None


def epar_indication_html(soup):
    """Narrow an EPAR page to the sections that can hold the indication.

    Authorised medicines carry a 'Therapeutic indication' subsection; medicines
    that have only just received a positive CHMP opinion have an 'Overview'
    section instead.
    """
    parts = []
    for pattern in (r'Therapeutic indication', r'^Overview$'):
        section = _section_for_heading(soup, pattern)
        if section is not None:
            parts.append(condense_html(section))
    return '\n'.join(parts) if parts else condense_html(soup)


def page_text(soup):
    """Plain visible text of a page, used for the NICE similarity comparison."""
    doc = BeautifulSoup(str(soup), 'html.parser')
    for tag in doc(_NOISE_TAGS):
        tag.decompose()
    return doc.get_text(separator=' ', strip=True)
