export const EMA_ORIGIN = 'https://www.ema.europa.eu';
export const NICE_ORIGIN = 'https://www.nice.org.uk';

/** CHMP news, filtered to the committee's own items. */
export const NEWS_URL =
  `${EMA_ORIGIN}/en/news?f%5B0%5D=ema_news_responsible_body%3A100002`;

export const MEETING_HIGHLIGHTS_PATH = /^\/en\/news\/meeting-highlights.*-chmp-.*/;

/**
 * EMA and NICE serve complete HTML to a normal browser User-Agent, so the
 * crawler parses markup directly instead of driving a browser. Playwright would
 * cost roughly two orders of magnitude more time and memory for no extra data.
 */
export const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

/** Polite defaults: this is a public sector site and the workload is tiny. */
export const DEFAULT_MAX_CONCURRENCY = 4;
export const MAX_REQUEST_RETRIES = 3;
export const REQUEST_TIMEOUT_SECS = 60;

/** Request labels for the Crawlee router. */
export const Label = {
  NewsListing: 'NEWS_LISTING',
  MeetingHighlights: 'MEETING_HIGHLIGHTS',
  Epar: 'EPAR',
  Variation: 'VARIATION',
  NiceSearch: 'NICE_SEARCH',
} as const;

export type RequestLabel = (typeof Label)[keyof typeof Label];
