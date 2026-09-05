/* Front end for ema-nice-tracker: kick off a run and follow it live. */

const runButton = document.querySelector('#run');
const hint = document.querySelector('#hint');
const progressPanel = document.querySelector('#progress');
const resultsPanel = document.querySelector('#results');
const log = document.querySelector('#log');
const summary = document.querySelector('#summary');
const table = document.querySelector('#table');

/** Columns worth showing in the browser; the spreadsheet has all of them. */
const PREVIEW_COLUMNS = [
  'Product Name', 'INN', 'Initial Approval', 'What changed',
  'Therapy Area', 'Cancer', 'Full Indication', 'New indication HTML',
  'Search Result in NICE',
];

const EMPTY = new Set(['', 'N/A', 'null', 'undefined']);

function append(message, level = 'info') {
  const line = document.createElement('span');
  if (level !== 'info') line.className = level;
  line.textContent = `${message}\n`;
  log.append(line);
  log.scrollTop = log.scrollHeight;
}

function markStage(stage) {
  const items = [...document.querySelectorAll('.stages li')];
  const index = items.findIndex((item) => item.dataset.stage === stage);
  if (index < 0) return;
  items.forEach((item, position) => {
    item.classList.toggle('active', position === index);
    item.classList.toggle('done', position < index);
  });
}

function finishStages() {
  document.querySelectorAll('.stages li').forEach((item) => {
    item.classList.remove('active');
    item.classList.add('done');
  });
}

function renderTable(rows) {
  table.replaceChildren();
  if (!rows.length) return;

  const columns = PREVIEW_COLUMNS.filter((column) => column in rows[0]);

  const head = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement('th');
    cell.textContent = column;
    head.append(cell);
  }

  const body = table.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    for (const column of columns) {
      const cell = line.insertCell();
      const value = row[column] == null ? '' : String(row[column]);
      if (EMPTY.has(value.trim())) {
        cell.textContent = '—';
        cell.className = 'empty';
      } else {
        cell.textContent = value;
      }
    }
  }
}

runButton.addEventListener('click', () => {
  const params = new URLSearchParams({
    summaries: document.querySelector('#summaries').checked ? '1' : '0',
    skipNice: document.querySelector('#skipNice').checked ? '1' : '0',
    skipLlm: document.querySelector('#skipLlm').checked ? '1' : '0',
  });

  runButton.disabled = true;
  runButton.textContent = 'Running…';
  hint.textContent = 'Leave this tab open until it finishes.';
  progressPanel.hidden = false;
  resultsPanel.hidden = true;
  log.replaceChildren();

  const stream = new EventSource(`/api/run?${params}`);

  stream.addEventListener('progress', (event) => {
    const { stage, message, level } = JSON.parse(event.data);
    markStage(stage);
    append(message, level);
  });

  stream.addEventListener('done', (event) => {
    const result = JSON.parse(event.data);
    finishStages();
    stream.close();

    summary.textContent =
      `${result.medicines} medicines from “${result.meeting.title}”.` +
      (result.checksPassed === false ? ' Some checks need a look — see the log above.' : '');
    renderTable(result.rows ?? []);
    resultsPanel.hidden = false;

    runButton.disabled = false;
    runButton.textContent = 'Build the dataset again';
    hint.textContent = 'Done.';
  });

  stream.addEventListener('failed', (event) => {
    append(JSON.parse(event.data).message, 'error');
    finishStages();
    stream.close();
    runButton.disabled = false;
    runButton.textContent = 'Try again';
    hint.textContent = 'The run stopped early.';
  });

  stream.onerror = () => {
    // EventSource fires this on a clean close too; only report a real drop.
    if (stream.readyState === EventSource.CLOSED) return;
    append('Lost the connection to the server.', 'error');
    stream.close();
    runButton.disabled = false;
    runButton.textContent = 'Try again';
  };
});
