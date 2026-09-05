"""Locating the latest CHMP Meeting Highlights news item and its links.

The notebook used to repeat this block three times; collecting everything once
keeps the EPAR list, the variation list and the news date consistent.
"""

import re
from datetime import datetime

from get_chmp_opinion_date import get_chmp_opinion_date
from http_utils import fetch_soup

NEWS_URL = 'https://www.ema.europa.eu/en/news?f%5B0%5D=ema_news_responsible_body%3A100002'
BASE_URL = 'https://www.ema.europa.eu'

MH_LINK_PATTERN = re.compile(r'^/en/news/meeting-highlights.*-chmp-.*')

# Section headings under which a medicine counts as positively recommended.
# 'new medicines' means a first authorisation; the rest are extensions.
INITIAL_APPROVAL_HEADINGS = ('positive recommendations on new medicines',)
EXTENSION_HEADINGS = (
    'positive recommendations on new therapeutic indications',
    'positive recommendations on extensions of indications',
    'positive recommendations on extensions of therapeutic indications',
)

# '... (CHMP) 20-23 July 2026' -> the meeting's last day
_MEETING_DATES = re.compile(r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})')


def section_kind(heading_text):
    """'Initial approval', 'Extension' or None for a Meeting Highlights heading."""
    text = heading_text.strip().lower()
    if any(h in text for h in INITIAL_APPROVAL_HEADINGS):
        return 'Initial approval'
    if any(h in text for h in EXTENSION_HEADINGS):
        return 'Extension'
    return None


def find_section_heading(item):
    """Return the section heading inside a Meeting Highlights `div.item`, if any.

    EMA now renders these as ``class="h2 mb-4 rounded-title"``; matching the
    exact former class string ``"mb-4 rounded-title"`` finds nothing, which
    silently dropped every medicine from the output.
    """
    return item.find(['h2', 'h3'], class_=lambda v: v and 'rounded-title' in v)


def absolute(href):
    return href if href.startswith('http') else BASE_URL + href


def meeting_end_date(title):
    """CHMP opinion date parsed from the news title, e.g. '20-23 July 2026'."""
    match = _MEETING_DATES.search(title)
    if not match:
        return 'N/A'
    day_to, month, year = match.group(2), match.group(3), match.group(4)
    try:
        return datetime.strptime(f'{day_to} {month} {year}', '%d %B %Y').strftime('%d %B %Y')
    except ValueError:
        return 'N/A'


def published_date(soup):
    """Publication date of a news page, taken from its first <time> element."""
    time_tag = soup.find('time')
    return time_tag.get_text(strip=True) if time_tag else 'N/A'


def collect_latest_meeting_highlights():
    """Return everything the pipeline needs from the newest Meeting Highlights.

    Returns a dict with: title, date, chmp_opinion_date, url, soup,
    epar_urls, variation_urls.
    """
    listing = fetch_soup(NEWS_URL)
    link = listing.find('a', href=MH_LINK_PATTERN)
    if link is None:
        raise RuntimeError(f'No Meeting Highlights link found on {NEWS_URL}')

    title = link.get_text(strip=True)
    url = absolute(link['href'])
    soup = fetch_soup(url)

    epar_urls, variation_urls = [], []
    kind = None
    for item in soup.find_all('div', class_='item'):
        heading = find_section_heading(item)
        if heading:
            kind = section_kind(heading.get_text(strip=True))
            continue
        if kind is None:
            continue

        product_tag = item.find('h3', class_='mb-4')
        if product_tag:
            slug = product_tag.get_text(strip=True).lower().replace(' ', '-')
            epar_urls.append(f'{BASE_URL}/en/medicines/human/EPAR/{slug}')

        # Variation links are now emitted as absolute URLs on most rows and as
        # site-relative paths on others; matching only '/en/...' missed most.
        for a_tag in item.find_all('a', href=True):
            if '/en/medicines/human/variation/' in a_tag['href']:
                variation_urls.append(absolute(a_tag['href']))

    date = published_date(soup)
    # The title is the primary source for the opinion date. If EMA changes how
    # the title is worded the regex stops matching, so fall back on the news
    # date: the meeting ends the day before EMA publishes the highlights.
    chmp_opinion_date = meeting_end_date(title)
    if chmp_opinion_date == 'N/A' and date != 'N/A':
        chmp_opinion_date = get_chmp_opinion_date(date)

    return {
        'title': title,
        'date': date,
        'chmp_opinion_date': chmp_opinion_date,
        'url': url,
        'soup': soup,
        'epar_urls': list(dict.fromkeys(epar_urls)),
        'variation_urls': list(dict.fromkeys(variation_urls)),
    }
