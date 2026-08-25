import { writeFile } from 'node:fs/promises';
import { log } from 'crawlee';

import { crawl } from './crawl.js';

/** Standalone entry point: crawl and write the raw dataset to a file. */

const output = process.argv[2] ?? 'crawl.json';

const result = await crawl({ skipNice: process.argv.includes('--skip-nice') });
await writeFile(output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');

log.info(
  `${result.medicines.length} medicines from "${result.meeting.title}" -> ${output}`,
);
