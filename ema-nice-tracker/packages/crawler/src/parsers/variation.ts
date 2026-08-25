import type { Dom } from './dom.js';
import { condense } from './html.js';

/**
 * Parsing an EMA variation page.
 *
 * EMA marks the change to a therapeutic indication as a character-level diff:
 * `<strong>` for text being added and `<s>` for text being removed. That means
 * the fragments are often mid-sentence ('an', '-based regimen'), which is why
 * the pipeline asks a model to stitch them into readable indications — but the
 * fragments themselves are an exact record of what changed, so they are kept
 * alongside the model's answer and used to check it.
 */

/** Bold text EMA puts on every page, unrelated to any indication. */
const BOILERPLATE = [
  'First published:',
  'This page was last updated on',
  'European Medicines Agency',
];

function fragments($: Dom, selector: string): string[] {
  const found: string[] = [];

  $(selector).each((_, element) => {
    const text = $(element).text().replace(/\s+/g, ' ').trim();
    if (!text) return;
    if (BOILERPLATE.some((b) => text.startsWith(b))) return;
    found.push(text);
  });

  return found;
}

/** Text marked as newly added. */
export function addedFragments($: Dom): string[] {
  return fragments($, 'strong');
}

/** Text marked as removed. */
export function removedFragments($: Dom): string[] {
  return fragments($, 's');
}

/** Trimmed page markup, with the diff tags intact. */
export function variationHtml($: Dom): string {
  return condense($);
}
