"""EPAR and NICE parsing, and the page-trimming that keeps requests in budget."""

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from http_utils import condense_html, epar_indication_html, page_text
from scrape_data_fromEPAR import scrape_data_fromEPAR
from scrape_data_fromNICE import scrape_data_fromNICE

# gpt-4o-mini has a 128k-token window. An untrimmed Keytruda EPAR page was
# ~200k tokens, which failed the request outright.
TOKEN_BUDGET = 30_000
CHARS_PER_TOKEN = 3.6

GROUP_COLUMN = 'Pharmacotherapeutic group\n(human)'


def approx_tokens(text):
    return len(text) / CHARS_PER_TOKEN


@pytest.fixture
def empty_sheet():
    return pd.DataFrame({'Name of medicine': [], GROUP_COLUMN: []})


@pytest.fixture
def therapy_areas():
    return pd.DataFrame({'Therapy Class': ['L01', 'C10'],
                         'Therapy Area': ['Cancer', 'Cardiovascular']})


@pytest.fixture
def blank_page(monkeypatch):
    """Serve an EPAR page with no ATC code, to exercise the fallback path."""
    import scrape_data_fromEPAR as module
    monkeypatch.setattr(
        module, 'fetch_soup',
        lambda url, attempts=3: BeautifulSoup('<html><body></body></html>', 'html.parser'),
    )
    return module


def test_atc_code_gives_therapy_class_and_cancer_flag(offline, empty_sheet, therapy_areas):
    data = scrape_data_fromEPAR(
        'https://www.ema.europa.eu/en/medicines/human/EPAR/keytruda',
        {'Product Name': 'keytruda'}, therapy_areas, empty_sheet,
    )
    assert data['Therapy class'] == 'L01'
    assert data['Cancer'] == 'Yes'
    assert data['Therapy Area'] == 'Cancer'


def test_recently_opinioned_medicine_resolves_its_therapy_area(offline, empty_sheet, therapy_areas):
    data = scrape_data_fromEPAR(
        'https://www.ema.europa.eu/en/medicines/human/EPAR/evlarco',
        {'Product Name': 'evlarco'}, therapy_areas, empty_sheet,
    )
    assert data['Therapy class'] == 'C10'
    assert data['Cancer'] == 'No'
    assert data['Therapy Area'] == 'Cardiovascular'


def test_page_without_atc_code_falls_back_to_the_medicine_list(blank_page, therapy_areas):
    """Some medicines carry no ATC code on the page until the Commission decides.

    Built from a stub page rather than a real medicine: any medicine used as the
    example would eventually gain an ATC code and fail for the wrong reason.
    """
    sheet = pd.DataFrame({'Name of medicine': ['stubbed'], GROUP_COLUMN: ['L01']})

    data = blank_page.scrape_data_fromEPAR(
        'https://example.invalid/stubbed', {'Product Name': 'stubbed'}, therapy_areas, sheet,
    )
    assert data['Therapy class'] == 'L01'
    assert data['Cancer'] == 'Yes'


def test_page_without_atc_code_or_sheet_row_degrades_to_na(blank_page, empty_sheet, therapy_areas):
    data = blank_page.scrape_data_fromEPAR(
        'https://example.invalid/unknown', {'Product Name': 'unknown'}, therapy_areas, empty_sheet,
    )
    assert data['Therapy class'] == 'N/A'
    assert data['Cancer'] == 'No'
    assert data['Therapy Area'] == 'N/A'


def test_epar_trimming_keeps_the_indication_and_fits_the_budget(soup):
    """Regression: the whole page used to be sent, blowing the context window."""
    trimmed = epar_indication_html(soup('epar_keytruda'))

    assert approx_tokens(trimmed) < TOKEN_BUDGET
    assert 'Therapeutic indication' in trimmed
    assert 'advanced (unresectable or metastatic) melanoma' in trimmed


def test_epar_trimming_falls_back_to_overview(soup):
    """Medicines awaiting authorisation have an Overview but no indication section."""
    trimmed = epar_indication_html(soup('epar_evlarco'))

    assert approx_tokens(trimmed) < TOKEN_BUDGET
    assert 'Overview' in trimmed


@pytest.mark.parametrize('name', ['variation_enhertu', 'variation_jivi', 'variation_repatha'])
def test_variation_trimming_preserves_the_diff_markup(soup, name):
    """The prompts key off <strong> and <s>; trimming must not strip them."""
    doc = soup(name)
    trimmed = condense_html(doc)

    assert approx_tokens(trimmed) < TOKEN_BUDGET
    if doc.find('strong'):
        assert '<strong>' in trimmed
    if doc.find('s'):
        assert '<s>' in trimmed


def test_nice_hit_and_miss(offline):
    hit = scrape_data_fromNICE('https://www.nice.org.uk/search?q=pembrolizumab',
                               {'INN': 'pembrolizumab'})
    miss = scrape_data_fromNICE('https://www.nice.org.uk/search?q=zzzznotadrugxyz',
                                {'INN': 'zzzznotadrugxyz'})
    assert hit['NICE'] == 'Yes'
    assert miss['NICE'] == 'N/A'


def test_nice_search_is_still_server_rendered(soup):
    """If NICE moved its results behind JavaScript, the text would come back bare."""
    text = page_text(soup('nice_pembrolizumab'))

    assert len(text) > 2000
    assert 'results for pembrolizumab' in text
    assert 'pembrolizumab' in text.lower()


def test_procedural_pdf_link_is_on_the_epar_page(offline):
    """Regression: this PDF used to be the one step downloaded by hand.

    The link carries no useful anchor text — it reads 'View' — so the fixed
    path segment is the only thing to match on. If EMA moves it, both PDF
    columns silently go back to 'N/A'.
    """
    from download_procedural_pdf import procedural_pdf_url

    url = procedural_pdf_url('https://www.ema.europa.eu/en/medicines/human/EPAR/keytruda')

    assert url is not None
    assert url.startswith('https://www.ema.europa.eu/')
    assert '/documents/procedural-steps-after/' in url
    # The '-archive' file holds the older history; the prompts want the current one.
    assert '-archive' not in url
    assert url.endswith('_en.pdf')


def test_a_medicine_with_only_an_opinion_has_no_procedural_pdf(offline):
    """A first authorisation has no post-authorisation history to download."""
    from download_procedural_pdf import procedural_pdf_url

    assert procedural_pdf_url(
        'https://www.ema.europa.eu/en/medicines/human/EPAR/evlarco') is None


def test_download_rejects_a_page_that_is_not_a_pdf(offline, monkeypatch, tmp_path):
    """EMA answers a moved document with 200 and HTML, which pypdf reads as empty."""
    import download_procedural_pdf as module

    class NotAPdf:
        content = b'<html>Page not found</html>'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(module.requests, 'get', lambda *a, **k: NotAPdf())

    with pytest.raises(RuntimeError, match='did not return a PDF'):
        module.download_procedural_pdf(
            'https://www.ema.europa.eu/en/medicines/human/EPAR/keytruda', tmp_path)


def test_download_reuses_a_file_already_on_disk(offline, monkeypatch, tmp_path):
    """Re-running the notebook must not re-fetch every PDF."""
    import download_procedural_pdf as module

    def refuse(*args, **kwargs):
        raise AssertionError('downloaded a PDF that was already on disk')

    epar = 'https://www.ema.europa.eu/en/medicines/human/EPAR/keytruda'
    name = module.procedural_pdf_url(epar).rsplit('/', 1)[-1]
    (tmp_path / name).write_bytes(b'%PDF-1.6 already here')
    monkeypatch.setattr(module.requests, 'get', refuse)

    assert module.download_procedural_pdf(epar, tmp_path) == str(tmp_path / name)
