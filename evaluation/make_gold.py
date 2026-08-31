"""Start a gold file: fill in what can be read off the page, leave the rest.

    python evaluation/make_gold.py -o evaluation/gold.csv

Two of the columns in a gold file are not judgement calls at all. EMA marks a
newly added indication in bold and a removed one in strikethrough, so
`New indication HTML` and `Removed indication HTML` can be pulled straight out
of the markup with BeautifulSoup — no model, no annotator. This script writes
those, plus the product names and the URLs, and leaves every other cell empty
for a person to fill in.

Nothing here calls the model, and nothing here imports the extraction prompts.
That is deliberate: a gold file produced by the thing it is meant to score is
not a gold file. The only step shared with the pipeline is fetching the page.

**What it cannot do, and why**

  * `Full Indication` — not mechanically derivable. Keytruda's therapeutic
    indication section is ~39,000 characters covering a dozen indications, and
    a medicine with only a positive opinion has no indication section at all,
    just an Overview paragraph with the indication inside the prose. Deciding
    what the answer is *is* the annotation.
  * `New indication PDF` / `EMA date for extension` — in the procedural steps
    PDFs, which are not downloaded by this script.
  * The three `... Similarity` columns — a yes/no judgement about two texts.
  * `What changed` — a written summary. If it were generated it would only
    measure whether one model agrees with another.

**A note on what does get filled**

The bold and strikethrough spans are a character-level diff, so they come out as
fragments ("A", "-based regimen", "or at high risk for") and sometimes twice
over, when a page repeats the indication in a heading and again in a paragraph.
Both are faithful to the page. Whether a repeat belongs in the gold answer is a
judgement call, so read the two columns before trusting them rather than after.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))

from ema_meeting_highlights import (BASE_URL, absolute, collect_latest_meeting_highlights,  # noqa: E402
                                    find_section_heading, section_kind)
from grounding import marked_up_fragments  # noqa: E402
from http_utils import fetch_soup  # noqa: E402

# The gold file's own columns, then two the annotator needs to click through.
COLUMNS = [
    'Product Name',
    'Full Indication',
    'New indication HTML',
    'New indication PDF',
    'Removed indication HTML',
    'EMA date for extension',
    'Search Result in NICE',
    'Full Indication Similarity',
    'New Indication HTML Similarity',
    'New Indication PDF Similarity',
    'What changed',
    'epar_url',
    'variation_url',
]

#: Cells this script fills in. Everything else is left for a person.
DERIVED = ('New indication HTML', 'Removed indication HTML')


def medicines_from_meeting(mh):
    """Product name and page URLs for every positively recommended medicine.

    Deliberately re-reads the meeting page rather than calling
    `scrape_data_fromMH_with_LLM`, which would pull the extraction prompts in.
    """
    medicines = []
    kind = None

    for item in mh['soup'].find_all('div', class_='item'):
        heading = find_section_heading(item)
        if heading:
            kind = section_kind(heading.get_text(strip=True))
            continue
        if kind is None:
            continue

        name_tag = item.find('h3', class_='mb-4')
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True).lower().replace(' ', '-')

        variation_urls = [
            absolute(a['href']) for a in item.find_all('a', href=True)
            if '/en/medicines/human/variation/' in a['href']
        ]
        if not variation_urls and kind == 'Extension':
            variation_urls = [f'{BASE_URL}/en/medicines/human/variation/{name}']

        medicines.append({
            'name': name,
            'kind': kind,
            'epar_url': f'{BASE_URL}/en/medicines/human/EPAR/{name}',
            'variation_urls': variation_urls,
        })

    return medicines


def diff_from_markup(variation_urls, fetch=fetch_soup):
    """The bold and strikethrough spans on a medicine's variation pages.

    Formatted the way the prompts ask for them — comma-separated, in page
    order — so the gold cell and a correct answer are directly comparable.
    """
    added, removed = [], []
    for url in variation_urls:
        try:
            soup = fetch(url)
        except Exception as e:
            print(f'  ! could not fetch {url}: {e}')
            continue
        added += marked_up_fragments(soup, 'strong')
        removed += marked_up_fragments(soup, 's')
    return ', '.join(added), ', '.join(removed)


def build_rows(fetch=fetch_soup):
    mh = collect_latest_meeting_highlights()
    print(f"Meeting Highlights: {mh['title']}")

    rows = []
    for medicine in medicines_from_meeting(mh):
        added, removed = diff_from_markup(medicine['variation_urls'], fetch)
        row = {column: '' for column in COLUMNS}
        row.update({
            'Product Name': medicine['name'],
            'New indication HTML': added,
            'Removed indication HTML': removed,
            'epar_url': medicine['epar_url'],
            'variation_url': ', '.join(medicine['variation_urls']),
        })
        rows.append(row)
        marked = 'no marked-up change' if not (added or removed) else \
            f'{len(added.split(", ")) if added else 0} added, ' \
            f'{len(removed.split(", ")) if removed else 0} removed'
        print(f'  {medicine["name"]:<28} {medicine["kind"]:<16} {marked}')

    return rows


def write(rows, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        # csv defaults to CRLF; this repo normalises to LF, so write LF directly
        # rather than leaving every generated gold file for git to rewrite.
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-o', '--output', default='evaluation/gold.csv')
    args = parser.parse_args()

    rows = build_rows()
    path = write(rows, args.output)

    filled = sum(1 for row in rows if any(row[column] for column in DERIVED))
    print(f'\nWrote {len(rows)} rows to {path}')
    print(f'  {filled} have a marked-up change, so their two diff columns are filled in')
    print(f'  {len(rows) - filled} are first authorisations, which have no diff to record')
    print('\nStill needs a person, in rough order of how much it is worth:')
    print('  What changed                 the reference summary')
    print('  Full Indication              copy the indication off the EPAR page')
    print('  the three Similarity columns Yes / No')
    print('  New indication PDF, EMA date for extension')
    print('                               only if you downloaded the procedural steps PDF')
    print('\nRead the two filled columns before trusting them: EMA marks a')
    print('character-level diff, so fragments and repeats are faithful to the page')
    print('but may not be the answer you want to score against.')


if __name__ == '__main__':
    main()
