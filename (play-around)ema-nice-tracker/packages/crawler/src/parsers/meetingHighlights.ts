import type { Dom, Nodes } from './dom.js';
import { EMA_ORIGIN, MEETING_HIGHLIGHTS_PATH, NICE_ORIGIN } from '../config.js';
import { definitionValue } from './html.js';
import type { MedicineRecord, RecommendationKind } from '../types.js';

/**
 * Parsing a CHMP Meeting Highlights news item.
 *
 * Each medicine is a `div.item`; the section headings that say whether a
 * medicine is newly approved or gaining an indication are `div.item` siblings
 * rather than parents, so the section is tracked while iterating.
 */

/** Section headings under which a medicine counts as positively recommended. */
const INITIAL_APPROVAL_HEADINGS = ['positive recommendations on new medicines'];
const EXTENSION_HEADINGS = [
  'positive recommendations on new therapeutic indications',
  'positive recommendations on extensions of indications',
  'positive recommendations on extensions of therapeutic indications',
];

const INN_LABEL = /International non-proprietary name \(INN\)|^INN$/;
const COMMON_NAME_LABEL = /Common name/;
const APPLICANT_LABEL = /Marketing[- ]authorisation applicant/i;
const HOLDER_LABEL = /Marketing[- ]authorisation holder/i;

const VARIATION_PATH = '/en/medicines/human/variation/';

/** '... (CHMP) 20-23 July 2026' -> the meeting's last day. */
const MEETING_DATES = /(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/;

const MONTHS = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
];

export function absolute(href: string): string {
  return href.startsWith('http') ? href : `${EMA_ORIGIN}${href}`;
}

/** URL of the newest Meeting Highlights item on the CHMP news listing. */
export function latestMeetingUrl($: Dom): { url: string; title: string } | null {
  let result: { url: string; title: string } | null = null;

  $('a[href]').each((_, anchor) => {
    if (result) return;
    const href = $(anchor).attr('href') ?? '';
    if (!MEETING_HIGHLIGHTS_PATH.test(href)) return;
    result = { url: absolute(href), title: $(anchor).text().trim() };
  });

  return result;
}

/**
 * The CHMP opinion date is the meeting's last day, taken from the news title.
 *
 * It used to be derived by subtracting a day from a `<time>` element on the
 * listing page; EMA removed that element, which silently blanked the column.
 */
export function chmpOpinionDate(title: string): string | null {
  const match = MEETING_DATES.exec(title);
  if (!match) return null;

  const [, , lastDay, monthName, year] = match;
  const month = MONTHS.indexOf(monthName.toLowerCase());
  if (month < 0) return null;

  const date = new Date(Date.UTC(Number(year), month, Number(lastDay)));
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

/** Publication date of the news item, from its first `<time>` element. */
export function publishedDate($: Dom): string | null {
  const time = $('time').first();
  return time.length ? time.text().trim() : null;
}

/**
 * The section heading inside a `div.item`, if that item is a heading.
 *
 * EMA renders these as `class="h2 mb-4 rounded-title"`. Matching the exact
 * former class string `"mb-4 rounded-title"` finds nothing, which is what
 * silently dropped every medicine from the output.
 */
export function sectionHeading($: Dom, item: Nodes): string | null {
  const heading = item.find('h2, h3').filter((_, element) =>
    (($(element).attr('class') ?? '').split(/\s+/)).includes('rounded-title'),
  ).first();

  return heading.length ? heading.text().trim() : null;
}

/** 'Initial approval', 'Extension', or null for sections to skip. */
export function recommendationKind(heading: string): RecommendationKind | null {
  const text = heading.toLowerCase();
  if (INITIAL_APPROVAL_HEADINGS.some((h) => text.includes(h))) return 'Initial approval';
  if (EXTENSION_HEADINGS.some((h) => text.includes(h))) return 'Extension';
  // Generics, biosimilars, negative opinions, withdrawals and statistics.
  return null;
}

/** Every positively recommended medicine on a Meeting Highlights page. */
export function parseMedicines($: Dom): MedicineRecord[] {
  const medicines: MedicineRecord[] = [];
  let kind: RecommendationKind | null = null;

  $('div.item').each((_, element) => {
    const item = $(element);

    const heading = sectionHeading($, item);
    if (heading !== null) {
      kind = recommendationKind(heading);
      return;
    }
    if (kind === null) return;

    const nameTag = item.find('h3.mb-4').first();
    if (!nameTag.length) return;

    const productName = nameTag.text().trim();
    const slug = productName.toLowerCase().replace(/\s+/g, '-');

    // Most variation links are absolute now and some are site-relative; the
    // old '/en/...' prefix check kept only the handful of relative ones.
    const variationUrls = new Set<string>();
    item.find('a[href]').each((__, anchor) => {
      const href = $(anchor).attr('href') ?? '';
      if (href.includes(VARIATION_PATH)) variationUrls.add(absolute(href));
    });

    const inn =
      definitionValue($, item, INN_LABEL) ?? definitionValue($, item, COMMON_NAME_LABEL);

    // EMA labels the company 'applicant' before the Commission decides and
    // 'holder' afterwards, so a full meeting needs both labels.
    const holder =
      definitionValue($, item, APPLICANT_LABEL) ?? definitionValue($, item, HOLDER_LABEL);

    medicines.push({
      productName,
      slug,
      inn,
      marketingAuthorisationHolder: holder,
      recommendation: kind,
      eparUrl: `${EMA_ORIGIN}/en/medicines/human/EPAR/${slug}`,
      variationUrls: [...variationUrls],
      niceUrl: inn ? `${NICE_ORIGIN}/search?q=${encodeURIComponent(inn)}` : null,
    });
  });

  return medicines;
}
