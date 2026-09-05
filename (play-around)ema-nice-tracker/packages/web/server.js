/**
 * Browser interface for ema-nice-tracker.
 *
 * A small dependency-free HTTP server: it serves one page, streams pipeline
 * progress over Server-Sent Events so a run that takes minutes shows what it is
 * doing, and hands back the finished dataset.
 */
import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { runPipeline } from '@ema-nice/cli/src/pipeline.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(HERE, 'public');

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

/** Where a run's artefacts go, relative to wherever the server was started. */
const WORK_DIR = resolve(process.env.EMA_NICE_WORK_DIR ?? '.ema-nice');
const PATHS = {
  dataset: join(WORK_DIR, 'dataset.xlsx'),
  preview: join(WORK_DIR, 'dataset.json'),
  crawl: join(WORK_DIR, 'crawl.json'),
  cache: join(WORK_DIR, 'cache'),
};

/** One run at a time: the pipeline hits external sites and costs API credit. */
let running = false;

function sendEvent(response, event, payload) {
  response.write(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`);
}

async function handleRun(request, response) {
  const params = new URL(request.url, 'http://localhost').searchParams;

  if (running) {
    response.writeHead(409, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ error: 'A run is already in progress.' }));
    return;
  }

  response.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });

  running = true;
  try {
    const summary = await runPipeline({
      output: PATHS.dataset,
      crawlPath: PATHS.crawl,
      cacheDir: PATHS.cache,
      previewPath: PATHS.preview,
      summaries: params.get('summaries') === '1',
      skipLlm: params.get('skipLlm') === '1',
      skipNice: params.get('skipNice') === '1',
      onEvent: (event) => sendEvent(response, 'progress', event),
    });

    let rows = [];
    try {
      rows = JSON.parse(await readFile(PATHS.preview, 'utf8'));
    } catch {
      // The preview is a convenience; the dataset itself is still on disk.
    }
    sendEvent(response, 'done', { ...summary, rows });
  } catch (error) {
    sendEvent(response, 'failed', { message: error.message });
  } finally {
    running = false;
    response.end();
  }
}

async function serveFile(path, response, { download = false } = {}) {
  try {
    const info = await stat(path);
    const headers = {
      'Content-Type': CONTENT_TYPES[extname(path)] ?? 'application/octet-stream',
      'Content-Length': info.size,
    };
    if (download) headers['Content-Disposition'] = 'attachment; filename="dataset.xlsx"';
    response.writeHead(200, headers);
    createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain' });
    response.end('Not found');
  }
}

export function startServer({ port = 3000 } = {}) {
  const server = createServer(async (request, response) => {
    const { pathname } = new URL(request.url, 'http://localhost');

    if (pathname === '/api/run') return handleRun(request, response);
    if (pathname === '/api/download') return serveFile(PATHS.dataset, response, { download: true });
    if (pathname === '/api/status') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      return response.end(JSON.stringify({ running, workDir: WORK_DIR }));
    }

    const file = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
    // Keep requests inside the public folder.
    const target = join(PUBLIC_DIR, file);
    if (!target.startsWith(PUBLIC_DIR)) {
      response.writeHead(403);
      return response.end('Forbidden');
    }
    return serveFile(target, response);
  });

  return new Promise((resolvePromise) => {
    server.listen(port, () => {
      console.log(`ema-nice-tracker is running at http://localhost:${port}`);
      console.log(`Output goes to ${WORK_DIR}`);
      resolvePromise(server);
    });
  });
}
