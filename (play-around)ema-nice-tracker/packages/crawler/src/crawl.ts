import { CheerioCrawler, createCheerioRouter, log, Configuration } from 'crawlee';

import type { RequestLabel } from './config.js';
import {
  DEFAULT_MAX_CONCURRENCY,
  Label,
  MAX_REQUEST_RETRIES,
  NEWS_URL,
  REQUEST_TIMEOUT_SECS,
  USER_AGENT,
} from './config.js';
import { indicationHtml, therapyClass } from './parsers/epar.js';
import {
  chmpOpinionDate,
  latestMeetingUrl,
  parseMedicines,
  publishedDate,
} from './parsers/meetingHighlights.js';
import { hasResults, searchResultsText } from './parsers/nice.js';
import { addedFragments, removedFragments, variationHtml } from './parsers/variation.js';
import type { CrawlOptions, CrawlResult, EnrichedMedicine } from './types.js';

/**
 * The crawl is a small, fixed graph rather than an open-ended spider:
 *
 *   news listing -> newest Meeting Highlights -> for each medicine:
 *                     EPAR page, variation page(s), NICE search
 *
 * Crawlee handles the queue, retries, throttling and error isolation, so one
 * unreachable EPAR page degrades a single medicine instead of the whole run.
 */

interface CrawlState {
  meeting: CrawlResult['meeting'] | null;
  medicines: Map<string, EnrichedMedicine>;
}

/** Which medicine a page belongs to; carried on the request. */
interface PageContext {
  slug: string;
  url: string;
}

/**
 * Which medicines a NICE page belongs to.
 *
 * Combination products share an INN, so two medicines can map to the same NICE
 * search URL. Crawlee de-duplicates requests by URL, so the page is fetched
 * once and the result is handed to every medicine that asked for it.
 */
interface NiceContext {
  slugs: string[];
  url: string;
}

/** A queued page, tagged so the router knows which handler to run. */
interface PageRequest {
  url: string;
  label: RequestLabel;
  userData: PageContext | NiceContext;
}

function blankMeeting(): CrawlResult['meeting'] {
  return { title: '', url: '', published: null, chmpOpinionDate: null };
}

export async function crawl(options: CrawlOptions = {}): Promise<CrawlResult> {
  const state: CrawlState = { meeting: null, medicines: new Map() };
  const router = createCheerioRouter();

  router.addHandler(Label.NewsListing, async ({ $, crawler, request }) => {
    const latest = latestMeetingUrl($);
    if (!latest) {
      throw new Error(`No Meeting Highlights link found on ${request.url}`);
    }
    log.info(`Latest meeting: ${latest.title}`);
    await crawler.addRequests([
      { url: latest.url, label: Label.MeetingHighlights, userData: { title: latest.title } },
    ]);
  });

  router.addHandler(Label.MeetingHighlights, async ({ $, crawler, request }) => {
    const title = (request.userData.title as string | undefined) ?? $('h1').first().text().trim();

    state.meeting = {
      title,
      url: request.url,
      published: publishedDate($),
      chmpOpinionDate: chmpOpinionDate(title),
    };

    const medicines = parseMedicines($);
    log.info(`${medicines.length} positively recommended medicines`);
    if (medicines.length === 0) {
      // Structural change on EMA's side: fail loudly instead of writing an
      // empty dataset, which is how this went unnoticed before.
      throw new Error(
        `Parsed 0 medicines from ${request.url}. EMA's markup has probably changed.`,
      );
    }

    for (const medicine of medicines) {
      state.medicines.set(medicine.slug, {
        ...medicine,
        therapyClass: null,
        indicationHtml: null,
        variationHtml: {},
        markedUpAdded: [],
        markedUpRemoved: [],
        niceText: null,
        niceHasResults: null,
      });
    }

    const followUps: PageRequest[] = medicines.flatMap((medicine) => [
      {
        url: medicine.eparUrl,
        label: Label.Epar,
        userData: { slug: medicine.slug, url: medicine.eparUrl },
      },
      ...medicine.variationUrls.map((url) => ({
        url,
        label: Label.Variation as RequestLabel,
        userData: { slug: medicine.slug, url },
      })),
    ]);

    if (!options.skipNice) {
      const niceTargets = new Map<string, string[]>();
      for (const medicine of medicines) {
        if (!medicine.niceUrl) continue;
        const slugs = niceTargets.get(medicine.niceUrl) ?? [];
        slugs.push(medicine.slug);
        niceTargets.set(medicine.niceUrl, slugs);
      }
      for (const [url, slugs] of niceTargets) {
        followUps.push({ url, label: Label.NiceSearch, userData: { slugs, url } });
      }
    }

    await crawler.addRequests(followUps);
  });

  router.addHandler(Label.Epar, async ({ $, request }) => {
    const { slug } = request.userData as PageContext;
    const medicine = state.medicines.get(slug);
    if (!medicine) return;

    medicine.therapyClass = therapyClass($);
    medicine.indicationHtml = indicationHtml($);
  });

  router.addHandler(Label.Variation, async ({ $, request }) => {
    const { slug, url } = request.userData as PageContext;
    const medicine = state.medicines.get(slug);
    if (!medicine) return;

    medicine.variationHtml[url] = variationHtml($);
    medicine.markedUpAdded.push(...addedFragments($));
    medicine.markedUpRemoved.push(...removedFragments($));
  });

  router.addHandler(Label.NiceSearch, async ({ $, request }) => {
    const { slugs } = request.userData as NiceContext;
    const found = hasResults($);
    const text = found ? searchResultsText($) : null;

    for (const slug of slugs) {
      const medicine = state.medicines.get(slug);
      if (!medicine) continue;
      medicine.niceHasResults = found;
      medicine.niceText = text;
    }
  });

  const crawler = new CheerioCrawler(
    {
      requestHandler: router,
      maxConcurrency: options.maxConcurrency ?? DEFAULT_MAX_CONCURRENCY,
      maxRequestRetries: MAX_REQUEST_RETRIES,
      requestHandlerTimeoutSecs: REQUEST_TIMEOUT_SECS,
      additionalMimeTypes: ['text/html'],
      preNavigationHooks: [
        async ({ request }) => {
          request.headers = { ...request.headers, 'User-Agent': USER_AGENT };
        },
      ],
      failedRequestHandler: ({ request }, error) => {
        // A medicine with an unreachable page still belongs in the output, with
        // the fields that page would have filled left null.
        log.warning(`Gave up on ${request.url}: ${error.message}`);
      },
    },
    // Keep Crawlee's bookkeeping out of the user's working directory.
    new Configuration({ persistStorage: false }),
  );

  const startUrl = options.meetingUrl ?? options.newsUrl ?? NEWS_URL;
  const startLabel = options.meetingUrl ? Label.MeetingHighlights : Label.NewsListing;
  await crawler.run([{ url: startUrl, label: startLabel }]);

  return {
    meeting: state.meeting ?? blankMeeting(),
    crawledAt: new Date().toISOString(),
    medicines: [...state.medicines.values()],
  };
}
