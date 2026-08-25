/** The contract between the Node crawler and the Python enrichment step. */

/** How a medicine reached this meeting's agenda. */
export type RecommendationKind = 'Initial approval' | 'Extension';

/** One medicine as it appears in a CHMP Meeting Highlights news item. */
export interface MedicineRecord {
  productName: string;
  /** Lower-cased, hyphenated form used in EMA URLs. */
  slug: string;
  inn: string | null;
  marketingAuthorisationHolder: string | null;
  recommendation: RecommendationKind;
  eparUrl: string;
  variationUrls: string[];
  niceUrl: string | null;
}

/** Everything scraped for one medicine, ready for LLM extraction. */
export interface EnrichedMedicine extends MedicineRecord {
  /** ATC therapeutic subgroup: the first three characters of the ATC code. */
  therapyClass: string | null;
  /** Trimmed EPAR markup containing the therapeutic indication. */
  indicationHtml: string | null;
  /** Trimmed variation markup, keyed by URL; <strong> and <s> are preserved. */
  variationHtml: Record<string, string>;
  /** Text EMA marked as added (bold) and removed (strikethrough). */
  markedUpAdded: string[];
  markedUpRemoved: string[];
  /** Plain text of the NICE search results page. */
  niceText: string | null;
  niceHasResults: boolean | null;
}

/** One crawl of the latest Meeting Highlights. */
export interface CrawlResult {
  meeting: {
    title: string;
    url: string;
    /** Publication date shown on the news page. */
    published: string | null;
    /** Last day of the meeting, parsed from the title: the CHMP opinion date. */
    chmpOpinionDate: string | null;
  };
  crawledAt: string;
  medicines: EnrichedMedicine[];
}

export interface CrawlOptions {
  /** Override the news listing, e.g. to re-crawl an older meeting. */
  newsUrl?: string;
  /** Crawl a specific Meeting Highlights page instead of the newest one. */
  meetingUrl?: string;
  /** Skip NICE entirely (faster, and useful when only EMA data is wanted). */
  skipNice?: boolean;
  maxConcurrency?: number;
}
