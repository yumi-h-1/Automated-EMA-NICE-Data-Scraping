/**
 * Re-download the saved pages the parser tests run against.
 *
 *   node packages/crawler/test/fetchFixtures.js
 *
 * The pipeline breaks when EMA changes their markup, not when the model has a
 * bad day, so these pin the structure the parsers depend on.
 */
import { writeFile, mkdir } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const FIXTURE_DIR = join(HERE, 'fixtures');

const EMA = 'https://www.ema.europa.eu';
const NICE = 'https://www.nice.org.uk';

export const FIXTURES = {
  emaNews: `${EMA}/en/news?f%5B0%5D=ema_news_responsible_body%3A100002`,
  meetingHighlights: `${EMA}/en/news/meeting-highlights-committee-medicinal-products-human-use-chmp-20-23-july-2026`,
  eparKeytruda: `${EMA}/en/medicines/human/EPAR/keytruda`,
  eparEvlarco: `${EMA}/en/medicines/human/EPAR/evlarco`,
  variationEnhertu: `${EMA}/en/medicines/human/variation/enhertu`,
  variationJivi: `${EMA}/en/medicines/human/variation/jivi`,
  niceHit: `${NICE}/search?q=pembrolizumab`,
  niceMiss: `${NICE}/search?q=zzzznotadrugxyz`,
};

const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

await mkdir(FIXTURE_DIR, { recursive: true });

for (const [name, url] of Object.entries(FIXTURES)) {
  const response = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  if (!response.ok) {
    console.error(`  ${name}: HTTP ${response.status}`);
    continue;
  }
  const html = await response.text();
  await writeFile(join(FIXTURE_DIR, `${name}.html.gz`), gzipSync(html));
  console.log(`  ${name.padEnd(20)} ${html.length.toLocaleString().padStart(9)} chars`);
}
