"""Test setup: put `scripts/` on the path and serve fixtures instead of the network."""

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))

from fetch_fixtures import FIXTURES, load  # noqa: E402

# Reverse map so a patched fetch_soup can answer by URL.
_BY_URL = {url: name for name, url in FIXTURES.items()}


@pytest.fixture
def html():
    """html('meeting_highlights') -> the saved HTML string."""
    return load


@pytest.fixture
def soup():
    """soup('meeting_highlights') -> a parsed fixture."""
    return lambda name: BeautifulSoup(load(name), 'html.parser')


@pytest.fixture
def offline(monkeypatch):
    """Replace fetch_soup everywhere with a fixture lookup.

    Any URL the code reaches for that has no fixture fails the test loudly,
    rather than silently going out to the network.
    """
    import http_utils

    def fake_fetch_soup(url, attempts=3):
        name = _BY_URL.get(url)
        if name is None:
            raise AssertionError(f'No fixture for {url}; add one to fetch_fixtures.py')
        return BeautifulSoup(load(name), 'html.parser')

    monkeypatch.setattr(http_utils, 'fetch_soup', fake_fetch_soup)
    for module in ('ema_meeting_highlights', 'scrape_data_fromEPAR',
                   'scrape_data_fromNICE', 'text_fromNICE', 'batch'):
        __import__(module)
        monkeypatch.setattr(sys.modules[module], 'fetch_soup', fake_fetch_soup, raising=False)
    return fake_fetch_soup
