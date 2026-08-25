# ema-nice-tracker

Builds a structured dataset of every medicine recommended at the most recent
CHMP meeting, with therapeutic indications extracted from EMA and each medicine
cross-referenced against NICE.

Successor to the notebook in [`../scripts`](../scripts) and
[`../notebooks`](../notebooks), which stays where it is and still works.

```
┌── Node ─────────────────────┐   ┌── Python ────────────────────────┐
│  Crawlee                    │   │  pandas · openai · rouge-score   │
│  EMA news → medicines       │──▶│  LLM extraction                  │
│  EPAR · variation · NICE    │   │  EMA reference tables            │
│  → crawl.json               │   │  quality checks → dataset.xlsx   │
└─────────────────────────────┘   └──────────────────────────────────┘
        ▲                                     ▲
        └──────── CLI  ·  web interface ──────┘
```

## Quick start

```bash
npm install
pip install -e analysis

cp .env.example .env          # add your OpenAI key
npm run web                   # then open http://localhost:3000
```

Or from the command line:

```bash
node packages/cli/src/index.js run --summaries
node packages/cli/src/index.js run --skip-llm     # no API key needed
```

## Why the two halves

Crawling is Node because Crawlee gives the request queue, retries, throttling
and per-request error isolation for free — one unreachable EPAR page degrades a
single medicine instead of the whole run. The crawl is a fixed graph, not an
open-ended spider:

```
news listing → newest Meeting Highlights → per medicine:
                 EPAR page · variation page(s) · NICE search
```

It uses `CheerioCrawler`, not a browser. EMA and NICE both serve complete HTML
to an ordinary User-Agent, so Playwright would cost far more time and memory for
exactly the same data. A full meeting is ~41 requests in under two seconds.

Enrichment is Python because that is where pandas, the OpenAI client, the Excel
readers and the scoring libraries are. The two halves meet at one file:
`crawl.json`, which holds the trimmed markup for every page.

## Commands

| Command | What it does |
|---|---|
| `... cli run` | crawl, build the dataset, then check it |
| `... cli run --skip-llm` | scrape only — no API key, indication columns stay empty |
| `... cli run --summaries` | add a plain-English “What changed” column |
| `... cli crawl` | crawl only, write `crawl.json` |
| `... cli web` | browser interface on port 3000 |
| `ema-nice-analysis check dataset.xlsx --crawl crawl.json` | re-run the checks on an existing dataset |

`--pdf-dir` points at a folder of procedural steps PDFs if you downloaded any;
they are the one input the crawler cannot fetch, because EMA does not link them
predictably.

## Reading the output

One row per medicine, 26 columns. `N/A` is **expected** for a brand-new
medicine's `Therapy class`, `Decision date` and `Orphan` — EMA does not assign
an ATC code or list the medicine until the Commission decides — and for every
NICE column when NICE has no result for that INN.

`N/A` is a **problem** in `Product Name`, `INN`, `Marketing authorisation holder`
or `Full Indication`. That means a page layout changed; `npm test` will say which
part.

Two columns to read critically:

- **`New indication HTML` / `Removed indication HTML`** come from EMA's bold and
  strikethrough markup, which is a character-level diff. Fragments like `"A"` or
  `"-based regimen"` are what the page actually marks up, not an extraction
  error. The `What changed` column exists to turn those back into a sentence.
- **The NICE similarity columns** compare against the NICE *search results page*,
  not the full guidance document. Read them as “does a NICE result look
  related”, not “NICE has appraised this indication”.

## Checking a run

Three layers, and only the last needs anyone to label anything.

**1. Regression tests — no labels.** The pipeline's real failure mode is EMA
changing their markup, not the model having a bad day. Saved pages in
`packages/crawler/test/fixtures/` pin the structure the parsers depend on.

```bash
npm test                                        # 16 tests, offline
node packages/crawler/test/fetchFixtures.js     # refresh the saved pages
```

**2. Grounding and agreement — no labels.** Every indication field is an
*extraction*: the answer is already on the page, so it can be verified without a
reference dataset.

- **Grounding** checks that every phrase the model returned actually appears in
  the source. Copied verbatim scores 1.0; an invented indication scores near 0.
- **Agreement** compares the dataset with EMA's own published exports. The
  post-authorisation table confirms which medicines really had an extension and
  on what date; the medicines table confirms the Commission decision dates.

Both run at the end of `cli run`, or on their own:

```bash
ema-nice-analysis check dataset.xlsx --crawl crawl.json
```

**3. Scored against a gold file — needs labels.** After layers 1 and 2 only a
handful of rows per meeting need a human look. The model is asked for three
different kinds of answer, so three different metrics apply: exact match for the
verbatim extractions (with ROUGE alongside to show how near the misses were),
exact match for the date, and accuracy/F1/kappa for the yes-no judgements.
ROUGE alone is not enough — an answer that flips a negation still scores
ROUGE-L ≈ 0.91 against the correct text.

## Layout

```
packages/
  crawler/     Crawlee + TypeScript. Parsers are plain functions over a DOM,
               so they unit-test against saved pages without a crawl.
  cli/         Argument parsing and the shared pipeline both front ends use.
  web/         Dependency-free HTTP server; progress streams over SSE.
analysis/
  ema_nice_analysis/
    prompts.py   every prompt sent to the model
    enrich.py    crawl.json → the dataset
    lookup.py    EMA's published reference tables
    checks.py    grounding and agreement checks
    cli.py       enrich / check
data/
  therapy_area.xlsx   ATC subgroup → therapy area
```

## Notes

- `cheerio` is pinned to the version Crawlee bundles. A different version
  resolves to a second copy whose types are structurally identical but not
  assignable, and the crawler stops compiling.
- EMA's reference tables are downloaded, not bundled, and refreshed every 12
  hours. A stale copy does not raise an error — it silently produces years-old
  decision dates, which is much harder to notice.
