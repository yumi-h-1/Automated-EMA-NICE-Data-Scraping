import type { Dom } from './dom.js';
import { condense, sectionForHeading } from './html.js';

/** Parsing an EPAR (European Public Assessment Report) page. */

const ATC_LABEL = /Anatomical therapeutic chemical \(ATC\) code/;

const THERAPEUTIC_INDICATION = /Therapeutic indication/i;
const OVERVIEW = /^Overview$/i;

/**
 * The ATC therapeutic subgroup: the first three characters of the ATC code.
 *
 * Medicines that only have a positive opinion carry no ATC code yet, so this
 * returns null and the caller falls back to EMA's medicines table.
 */
export function therapyClass($: Dom): string | null {
  let code: string | null = null;

  $('dt').each((_, term) => {
    if (code !== null) return;
    if (!ATC_LABEL.test($(term).text().trim())) return;
    const value = $(term).nextAll('dd').first().text().trim();
    if (value) code = value.slice(0, 3);
  });

  return code;
}

/**
 * The part of an EPAR page that can hold the indication.
 *
 * Authorised medicines have a 'Therapeutic indication' subsection; medicines
 * that have only just received a positive opinion have an 'Overview' instead.
 * Sending the whole page instead cost ~200k tokens and simply failed.
 */
export function indicationHtml($: Dom): string | null {
  const parts: string[] = [];

  for (const pattern of [THERAPEUTIC_INDICATION, OVERVIEW]) {
    const section = sectionForHeading($, pattern);
    if (section) parts.push(condense($, section));
  }

  if (parts.length) return parts.join('\n');
  return condense($) || null;
}
