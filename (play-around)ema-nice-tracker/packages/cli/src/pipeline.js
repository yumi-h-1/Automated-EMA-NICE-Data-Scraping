/**
 * The pipeline, shared by the CLI and the web UI.
 *
 *   crawl  ->  crawl.json  ->  enrich  ->  dataset  ->  check
 *
 * Progress is reported through `onEvent` so both front ends can show the same
 * thing without either of them owning the logic.
 */
import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

import { crawl } from '@ema-nice/crawler';

import { runAnalysis } from './python.js';

/** @typedef {{ stage: string, message: string, level?: 'info'|'warn'|'error' }} PipelineEvent */

export const STAGES = ['crawl', 'enrich', 'check'];

export async function runPipeline(options = {}) {
  const {
    output = 'dataset.xlsx',
    crawlPath = 'crawl.json',
    pdfDir = null,
    cacheDir = '.cache',
    previewPath = null,
    summaries = false,
    skipLlm = false,
    skipNice = false,
    crawlOnly = false,
    check = true,
    onEvent = () => {},
  } = options;

  const emit = (stage, message, level = 'info') => onEvent({ stage, message, level });

  emit('crawl', 'Looking up the latest CHMP Meeting Highlights…');
  const result = await crawl({ skipNice });

  const outputPath = resolve(output);
  const crawlFile = resolve(crawlPath);
  await mkdir(dirname(crawlFile), { recursive: true });
  await writeFile(crawlFile, `${JSON.stringify(result, null, 2)}\n`, 'utf8');

  emit('crawl', `${result.meeting.title}`);
  emit('crawl', `${result.medicines.length} medicines collected → ${crawlFile}`);

  if (crawlOnly) {
    return { meeting: result.meeting, medicines: result.medicines.length, crawlFile, outputPath: null };
  }

  emit('enrich', skipLlm
    ? 'Assembling the dataset (model calls skipped)…'
    : 'Extracting indications with the model…');

  const enrichArgs = [
    'enrich', crawlFile,
    '-o', outputPath,
    '--cache-dir', resolve(cacheDir),
    ...(pdfDir ? ['--pdf-dir', resolve(pdfDir)] : []),
    ...(previewPath ? ['--preview', resolve(previewPath)] : []),
    ...(summaries ? ['--summaries'] : []),
    ...(skipLlm ? ['--skip-llm'] : []),
  ];

  const enrichCode = await runAnalysis(enrichArgs, {
    onLine: (line) => line.trim() && emit('enrich', line),
  });
  if (enrichCode !== 0) {
    throw new Error(`Enrichment failed (exit code ${enrichCode}).`);
  }

  if (!check) {
    return { meeting: result.meeting, medicines: result.medicines.length, crawlFile, outputPath };
  }

  emit('check', 'Running the quality checks…');
  const checkCode = await runAnalysis(
    ['check', outputPath, '--crawl', crawlFile, '--cache-dir', resolve(cacheDir)],
    { onLine: (line) => line.trim() && emit('check', line) },
  );

  // A non-zero exit means findings to read, not a crash.
  if (checkCode !== 0) {
    emit('check', 'Some checks need a look — see the findings above.', 'warn');
  }

  return {
    meeting: result.meeting,
    medicines: result.medicines.length,
    crawlFile,
    outputPath,
    checksPassed: checkCode === 0,
  };
}
