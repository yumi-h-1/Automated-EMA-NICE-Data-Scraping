import type { CheerioCrawlingContext } from 'crawlee';

/**
 * The DOM types the parsers work with.
 *
 * These are taken from the context Crawlee hands to a request handler rather
 * than imported from `cheerio` directly. Cheerio ships separate ESM and CJS
 * declaration trees, and importing the ESM one here would produce a type that
 * is structurally identical to — but not assignable from — the CJS one Crawlee
 * actually passes in.
 */
export type Dom = CheerioCrawlingContext['$'];

/** A selected set of nodes, as returned by `$(selector)`. */
export type Nodes = ReturnType<Dom>;
