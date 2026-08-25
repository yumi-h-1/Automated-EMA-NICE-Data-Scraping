"""The parsing steps that silently produced an empty dataset when EMA redesigned.

Every assertion here corresponds to something that actually broke: the section
heading class gained an 'h2' prefix, variation links became absolute, and the
<time> element disappeared from the news listing.
"""

from ema_meeting_highlights import (
    MH_LINK_PATTERN,
    collect_latest_meeting_highlights,
    find_section_heading,
    meeting_end_date,
    section_kind,
)

EXPECTED_MEDICINES = 16
EXPECTED_VARIATIONS = 8


def test_news_listing_still_links_to_meeting_highlights(soup):
    links = soup('ema_news').find_all('a', href=MH_LINK_PATTERN)
    assert links, 'no Meeting Highlights link on the news listing'
    assert 'chmp' in links[0]['href']


def test_section_headings_are_found(soup):
    """Regression: matching the exact class string 'mb-4 rounded-title' found none."""
    items = soup('meeting_highlights').find_all('div', class_='item')
    headings = [find_section_heading(i) for i in items]
    assert sum(h is not None for h in headings) >= 5


def test_section_kinds_are_classified(soup):
    items = soup('meeting_highlights').find_all('div', class_='item')
    kinds = {section_kind(h.get_text(strip=True))
             for h in (find_section_heading(i) for i in items) if h}
    assert 'Initial approval' in kinds
    assert 'Extension' in kinds
    # Generics, biosimilars, negative opinions and withdrawals stay excluded.
    assert None in kinds


def test_meeting_end_date_comes_from_the_title():
    """The news listing no longer carries a <time> element to subtract a day from."""
    title = ('Meeting highlights from the Committee for Medicinal Products '
             'for Human Use (CHMP) 20-23 July 2026')
    assert meeting_end_date(title) == '23 July 2026'
    assert meeting_end_date('no dates here') == 'N/A'


def test_collects_every_medicine_and_variation(offline):
    mh = collect_latest_meeting_highlights()

    assert len(mh['epar_urls']) == EXPECTED_MEDICINES
    assert len(mh['variation_urls']) == EXPECTED_VARIATIONS
    assert mh['chmp_opinion_date'] == '23 July 2026'
    assert mh['date'] != 'N/A'


def test_variation_urls_are_absolute_and_unique(offline):
    """Regression: EMA now emits most of these as absolute URLs, and the old
    startswith('/en/...') check kept only the single relative one."""
    urls = collect_latest_meeting_highlights()['variation_urls']

    assert all(u.startswith('https://www.ema.europa.eu/en/medicines/human/variation/') for u in urls)
    assert len(set(urls)) == len(urls)
    assert any(u.endswith('/enhertu') for u in urls)


def test_definition_lists_still_yield_inn_and_holder(soup, offline):
    """Every medicine must resolve an INN and a company.

    EMA labels the company 'Marketing authorisation applicant' for medicines
    awaiting a decision and 'holder' for authorised ones, so both labels are
    needed to cover a full meeting.
    """
    from scrape_data_fromMH_with_LLM import (
        _APPLICANT_LABEL, _COMMON_NAME_LABEL, _HOLDER_LABEL, _INN_LABEL, _definition,
    )

    items = soup('meeting_highlights').find_all('div', class_='item')
    inns = [_definition(i, _INN_LABEL) or _definition(i, _COMMON_NAME_LABEL) for i in items]
    companies = [_definition(i, _APPLICANT_LABEL) or _definition(i, _HOLDER_LABEL) for i in items]

    assert sum(v is not None for v in inns) >= EXPECTED_MEDICINES
    assert sum(v is not None for v in companies) >= EXPECTED_MEDICINES
