import type { Dom, Nodes } from './dom.js';

/**
 * Trimming pages before they reach the language model.
 *
 * EMA pages carry a lot of navigation, scripts and document tables that have
 * nothing to do with an indication. An untrimmed Keytruda EPAR page is roughly
 * 200k tokens, which does not fit in the model's context window at all.
 */

/** Tags that never carry content the pipeline cares about. */
const NOISE_TAGS = [
  'script', 'style', 'noscript', 'svg', 'head', 'nav', 'footer',
  'form', 'iframe', 'link', 'meta', 'button', 'picture', 'source',
];

/** Class names EMA uses for the container around a heading and its content. */
const SECTION_CLASSES = ['subsection', 'section'];

function stripNoise(scope: Nodes): void {
  scope.find(NOISE_TAGS.join(',')).remove();
}

/**
 * Strip noise and every attribute, keeping the markup the prompts rely on.
 *
 * `<strong>` (newly added indication) and `<s>` (removed indication) survive:
 * EMA marks up a character-level diff with those tags and the extraction
 * prompts key off exactly them.
 */
export function condense($: Dom, scope?: Nodes): string {
  const clone = (scope ?? $('body')).clone();

  stripNoise(clone);
  clone.find('*').each((_, element) => {
    const node = element as { attribs?: Record<string, string> };
    if (node.attribs) node.attribs = {};
  });

  return ($.html(clone) ?? '').replace(/\n\s*\n+/g, '\n').trim();
}

/** Visible text of a page, with the noise removed. */
export function plainText($: Dom, scope?: Nodes): string {
  const clone = (scope ?? $('body')).clone();
  stripNoise(clone);
  return clone.text().replace(/\s+/g, ' ').trim();
}

/** The smallest section container whose heading matches `pattern`. */
export function sectionForHeading($: Dom, pattern: RegExp): Nodes | null {
  let found: Nodes | null = null;

  $('h2, h3').each((_, heading) => {
    if (found) return;
    if (!pattern.test($(heading).text().trim())) return;

    let node = $(heading).parent();
    for (let depth = 0; depth < 4 && node.length > 0; depth += 1) {
      const classes = (node.attr('class') ?? '').split(/\s+/);
      if (SECTION_CLASSES.some((c) => classes.includes(c))) {
        found = node;
        return;
      }
      node = node.parent();
    }
    found = $(heading).parent();
  });

  return found;
}

/** Value of the `<dd>` following a `<dt>` whose label matches `pattern`. */
export function definitionValue(
  $: Dom,
  scope: Nodes,
  pattern: RegExp,
): string | null {
  let value: string | null = null;

  scope.find('dt').each((_, term) => {
    if (value !== null) return;
    if (!pattern.test($(term).text().trim())) return;
    const description = $(term).nextAll('dd').first();
    if (description.length) value = description.text().trim();
  });

  return value;
}
