/**
 * Running the Python analysis half from Node.
 *
 * The crawl is Node; the enrichment, dataset assembly and quality checks are
 * Python, because that is where pandas, the OpenAI client and the scoring
 * libraries live. This module is the only place the two halves meet.
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ANALYSIS_DIR = join(HERE, '..', '..', '..', 'analysis');

/** Interpreters to try, in order of preference. */
const CANDIDATES = [
  process.env.EMA_NICE_PYTHON,
  join(ANALYSIS_DIR, '.venv', 'bin', 'python'),
  'python3',
  'python',
].filter(Boolean);

export function findPython() {
  for (const candidate of CANDIDATES) {
    if (candidate.includes('/') && !existsSync(candidate)) continue;
    return candidate;
  }
  return 'python3';
}

/**
 * Run `ema-nice-analysis <args>`, streaming its output to `onLine`.
 * Resolves with the exit code rather than rejecting, so the caller decides
 * whether a non-zero result is fatal.
 */
export function runAnalysis(args, { onLine = () => {}, cwd = ANALYSIS_DIR } = {}) {
  return new Promise((resolve, reject) => {
    const python = findPython();
    const child = spawn(python, ['-m', 'ema_nice_analysis.cli', ...args], {
      cwd,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    let buffer = '';
    const consume = (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) onLine(line);
    };

    child.stdout.on('data', consume);
    child.stderr.on('data', consume);

    child.on('error', (error) =>
      reject(
        new Error(
          `Could not run Python ("${python}"): ${error.message}\n` +
            'Install the analysis package with:\n' +
            `  cd ${ANALYSIS_DIR} && pip install -e .`,
        ),
      ),
    );
    child.on('close', (code) => {
      if (buffer) onLine(buffer);
      resolve(code ?? 0);
    });
  });
}
