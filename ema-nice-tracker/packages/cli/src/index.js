#!/usr/bin/env node
/**
 * ema-nice-tracker — build the CHMP/NICE dataset for the latest meeting.
 *
 *   ema-nice-tracker run                     everything, into dataset.xlsx
 *   ema-nice-tracker run --skip-llm          scrape only, no API key needed
 *   ema-nice-tracker run --summaries         add a plain-English "What changed"
 *   ema-nice-tracker crawl -o crawl.json     just the crawl
 *   ema-nice-tracker web                     open the browser interface
 */
import { parseArgs } from 'node:util';

import { runPipeline } from './pipeline.js';

const USAGE = `
ema-nice-tracker <command> [options]

Commands
  run       crawl EMA and NICE, build the dataset, then check it
  crawl     crawl only, and write the raw pages to a JSON file
  web       start the browser interface on http://localhost:3000

Options
  -o, --output <file>    dataset file to write: .xlsx, .csv or .json  (dataset.xlsx)
      --crawl-file <f>   where to keep the raw crawl                  (crawl.json)
      --pdf-dir <dir>    folder of procedural steps PDFs, if you have any
      --cache-dir <dir>  where to keep EMA's reference tables         (.cache)
      --summaries        add a plain-English "What changed" column
      --skip-llm         build the dataset without calling the model
      --skip-nice        do not look anything up on NICE
      --no-check         skip the quality checks at the end
      --port <number>    port for "web"                               (3000)
  -h, --help             show this message
`.trim();

const OPTIONS = {
  output: { type: 'string', short: 'o', default: 'dataset.xlsx' },
  'crawl-file': { type: 'string', default: 'crawl.json' },
  'pdf-dir': { type: 'string' },
  'cache-dir': { type: 'string', default: '.cache' },
  summaries: { type: 'boolean', default: false },
  'skip-llm': { type: 'boolean', default: false },
  'skip-nice': { type: 'boolean', default: false },
  check: { type: 'boolean', default: true },
  port: { type: 'string', default: '3000' },
  help: { type: 'boolean', short: 'h', default: false },
};

const STAGE_LABEL = { crawl: 'crawl', enrich: 'enrich', check: 'check' };

function report({ stage, message, level }) {
  const prefix = `[${STAGE_LABEL[stage] ?? stage}]`.padEnd(9);
  const stream = level === 'error' ? process.stderr : process.stdout;
  stream.write(`${prefix} ${message}\n`);
}

async function main() {
  let parsed;
  try {
    parsed = parseArgs({ options: OPTIONS, allowPositionals: true });
  } catch (error) {
    console.error(`${error.message}\n\n${USAGE}`);
    process.exit(2);
  }

  const { values, positionals } = parsed;
  const command = positionals[0];

  if (values.help || !command) {
    // Asking for help succeeds; forgetting the command does not.
    console.log(USAGE);
    process.exit(values.help ? 0 : 1);
  }

  if (command === 'web') {
    const { startServer } = await import('../../web/server.js');
    await startServer({ port: Number(values.port) });
    return;
  }

  if (command !== 'run' && command !== 'crawl') {
    console.error(`Unknown command "${command}".\n\n${USAGE}`);
    process.exit(2);
  }

  const summary = await runPipeline({
    output: values.output,
    crawlPath: values['crawl-file'],
    pdfDir: values['pdf-dir'],
    cacheDir: values['cache-dir'],
    summaries: values.summaries,
    skipLlm: values['skip-llm'],
    skipNice: values['skip-nice'],
    crawlOnly: command === 'crawl',
    check: values.check,
    onEvent: report,
  });

  if (summary.outputPath) {
    console.log(`\nDone — ${summary.medicines} medicines → ${summary.outputPath}`);
  } else {
    console.log(`\nDone — ${summary.medicines} medicines → ${summary.crawlFile}`);
  }
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exit(1);
});
