/**
 * Parser regression tests, run offline against saved pages.
 *
 * Every assertion here corresponds to something that actually broke when EMA
 * redesigned their site: the section heading class gained an 'h2' prefix,
 * variation links became absolute, the <time> element left the news listing,
 * and untrimmed EPAR pages stopped fitting in the model's context window.
 */
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join } from 'node:path';
import { test, describe } from 'node:test';

import { load } from 'cheerio';

import { FIXTURE_DIR } from './fetchFixtures.js';
import { indicationHtml, therapyClass } from '../dist/parsers/epar.js';
import {
  chmpOpinionDate,
  latestMeetingUrl,
  parseMedicines,
  publishedDate,
  recommendationKind,
} from '../dist/parsers/meetingHighlights.js';
import { hasResults, searchResultsText } from '../dist/parsers/nice.js';
import { addedFragments, removedFragments, variationHtml } from '../dist/parsers/variation.js';

const EXPECTED_MEDICINES = 16;
const EXPECTED_VARIATIONS = 8;

// gpt-4o-mini has a 128k-token window; an untrimmed EPAR page was ~200k.
const TOKEN_BUDGET = 30_000;
const CHARS_PER_TOKEN = 3.6;

const dom = (name) =>
  load(gunzipSync(readFileSync(join(FIXTURE_DIR, `${name}.html.gz`))).toString('utf8'));

const approxTokens = (text) => text.length / CHARS_PER_TOKEN;

describe('meeting highlights', () => {
  test('the news listing still links to a Meeting Highlights item', () => {
    const latest = latestMeetingUrl(dom('emaNews'));
    assert.ok(latest, 'no Meeting Highlights link found');
    assert.match(latest.url, /meeting-highlights.*chmp/);
  });

  test('the CHMP opinion date is read from the news title', () => {
    // The listing page no longer carries a <time> element to subtract a day from.
    assert.equal(
      chmpOpinionDate('Meeting highlights from the CHMP 20-23 July 2026'),
      '2026-07-23',
    );
    assert.equal(chmpOpinionDate('no dates in this title'), null);
  });

  test('the news page still carries a publication date', () => {
    assert.ok(publishedDate(dom('meetingHighlights')));
  });

  test('section headings map to a recommendation kind', () => {
    assert.equal(
      recommendationKind('Positive recommendations on new medicines'),
      'Initial approval',
    );
    assert.equal(
      recommendationKind('Positive recommendations on extensions of therapeutic indications'),
      'Extension',
    );
    // Generics, biosimilars and negative opinions stay out of the dataset.
    assert.equal(recommendationKind('Positive recommendations on new generic medicines'), null);
    assert.equal(recommendationKind('Negative recommendations on new medicines'), null);
  });

  test('every positively recommended medicine is found', () => {
    // Regression: matching the exact class string 'mb-4 rounded-title' matched
    // nothing after EMA's redesign, so this returned zero medicines.
    const medicines = parseMedicines(dom('meetingHighlights'));

    assert.equal(medicines.length, EXPECTED_MEDICINES);
    assert.ok(medicines.every((m) => m.inn), 'a medicine is missing its INN');
    assert.ok(
      medicines.every((m) => m.marketingAuthorisationHolder),
      'a medicine is missing its marketing authorisation holder',
    );
    assert.ok(medicines.some((m) => m.recommendation === 'Initial approval'));
    assert.ok(medicines.some((m) => m.recommendation === 'Extension'));
  });

  test('variation links are collected as absolute URLs', () => {
    // Regression: EMA emits most of these as absolute URLs now, and checking
    // for a leading '/en/' kept only the single relative one.
    const medicines = parseMedicines(dom('meetingHighlights'));
    const urls = medicines.flatMap((m) => m.variationUrls);

    assert.equal(urls.length, EXPECTED_VARIATIONS);
    assert.equal(new Set(urls).size, urls.length, 'duplicate variation URLs');
    assert.ok(urls.every((u) => u.startsWith('https://www.ema.europa.eu/en/medicines/human/variation/')));
  });

  test('only extensions carry variation links', () => {
    const medicines = parseMedicines(dom('meetingHighlights'));
    for (const medicine of medicines) {
      if (medicine.recommendation === 'Initial approval') {
        assert.equal(medicine.variationUrls.length, 0, `${medicine.productName} has a variation URL`);
      }
    }
  });
});

describe('EPAR pages', () => {
  test('the ATC therapeutic subgroup is read from the page', () => {
    assert.equal(therapyClass(dom('eparKeytruda')), 'L01');
  });

  test('a page with no ATC code returns null so the caller can fall back', () => {
    assert.equal(therapyClass(load('<html><body></body></html>')), null);
  });

  test('trimming keeps the indication and fits the context window', () => {
    const trimmed = indicationHtml(dom('eparKeytruda'));

    assert.ok(approxTokens(trimmed) < TOKEN_BUDGET, `${approxTokens(trimmed)} tokens`);
    assert.match(trimmed, /Therapeutic indication/);
    assert.match(trimmed, /advanced \(unresectable or metastatic\) melanoma/);
  });

  test('a medicine awaiting authorisation falls back to its Overview', () => {
    const trimmed = indicationHtml(dom('eparEvlarco'));

    assert.ok(approxTokens(trimmed) < TOKEN_BUDGET);
    assert.match(trimmed, /Overview/);
  });
});

describe('variation pages', () => {
  test('added text is extracted and boilerplate is ignored', () => {
    const added = addedFragments(dom('variationEnhertu'));

    assert.ok(added.length > 0);
    assert.ok(!added.some((f) => f.startsWith('First published:')));
    assert.match(added.join(' '), /in combination with pertuzumab/);
  });

  test('removed text is extracted', () => {
    assert.deepEqual(removedFragments(dom('variationJivi')), ['previously treated']);
  });

  test('trimming preserves the diff markup the prompts rely on', () => {
    const trimmed = variationHtml(dom('variationEnhertu'));

    assert.ok(approxTokens(trimmed) < TOKEN_BUDGET);
    assert.match(trimmed, /<strong>/);
  });
});

describe('NICE search', () => {
  test('a hit and a miss are told apart', () => {
    assert.equal(hasResults(dom('niceHit')), true);
    assert.equal(hasResults(dom('niceMiss')), false);
  });

  test('results are still server-rendered', () => {
    // If NICE moved its listing behind JavaScript, this would come back bare.
    const text = searchResultsText(dom('niceHit'));

    assert.ok(text.length > 2000, `only ${text.length} chars of text`);
    assert.match(text, /results for pembrolizumab/);
  });
});
