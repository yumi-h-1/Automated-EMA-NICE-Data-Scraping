import type { Dom } from './dom.js';
import { plainText } from './html.js';

/**
 * Parsing a NICE search results page.
 *
 * NICE titles read '<query> | Search results | NICE', or
 * 'No results | Search results | NICE' when nothing matched. The first segment
 * is NICE echoing the query back, so it confirms that results exist rather than
 * that any particular medicine was found.
 */

export function hasResults($: Dom): boolean {
  const title = $('title').first().text().trim();
  return title.length > 0 && !title.startsWith('No results');
}

/** Plain text of the results listing, used for the indication comparison. */
export function searchResultsText($: Dom): string {
  return plainText($);
}
