# Automated EMA & NICE Data Scraping

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/GPT--4o_mini-412991?style=flat&logo=openai&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat&logo=pandas&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup4-43B02A?style=flat&logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat&logo=langchain&logoColor=white)
![Chroma](https://img.shields.io/badge/Chroma-FF6F61?style=flat&logo=databricks&logoColor=white)
![pypdf](https://img.shields.io/badge/pypdf-FF0000?style=flat&logo=adobeacrobatreader&logoColor=white)
![Jupyter](https://img.shields.io/badge/Jupyter-F37626?style=flat&logo=jupyter&logoColor=white)
![Google Colab](https://img.shields.io/badge/Google_Colab-F9AB00?style=flat&logo=googlecolab&logoColor=white)

Automated pipeline for building a structured regulatory and HTA (Health Technology Assessment) database on medicines, by combining web scraping, LLM-based extraction and retrieval-grounded summarisation from [EMA](https://www.ema.europa.eu) and [NICE](https://www.nice.org.uk).

---

## Pipeline

```mermaid
flowchart LR
    A["EMA & NICE\npages, PDFs"] --> B["Scrape\n+ trim"]
    B --> C["Extract\nGPT-4o mini"]
    B --> D["Chunk + embed\nLangChain → Chroma"]
    D --> E["Summarise\nGPT-4o mini"]
    C --> F["dataset\n25 columns + 2"]
    E --> F
```

---

## Output Dataset

Each row represents one medicine from the latest CHMP Meeting Highlights. 25 features are collected per medicine across four categories, plus two more when the summary step has run.

### Identification

| Feature | Description | Source |
|---|---|---|
| `Product Name` | Brand name | CHMP Meeting Highlights |
| `INN` | Molecule (international non-proprietary name) | CHMP Meeting Highlights |
| `Marketing authorisation holder` | Company name | CHMP Meeting Highlights |
| `epar_url` | Link to EPAR page | Generated from product name |
| `variation_url` | Link to variation page | Scraped from CHMP news |
| `MH_url` | Link to Meeting Highlights news | CHMP Meeting Highlights |

### Clinical

| Feature | Description | Source |
|---|---|---|
| `Full Indication` | Full therapeutic indication (LLM-extracted) | EPAR page |
| `New indication HTML` | Newly added indication shown in **bold** (LLM-extracted) | Variation page |
| `New indication PDF` | Most recently added indication (LLM-extracted) | Procedure steps PDF |
| `Removed indication HTML` | Removed indication shown in ~~strikethrough~~ (LLM-extracted) | Variation page |
| `Therapy class` | ATC code (first 3 characters) | EPAR page or medicine list |
| `Therapy Area` | Mapped therapy area | Therapy area lookup table |
| `Cancer` | Whether oncology drug (L01/L02) | Derived from therapy class |
| `Orphan` | Orphan medicine designation | EMA medicine list |

### Summary (optional — added by `summarise.add_summaries`)

| Feature | Description | Source |
|---|---|---|
| `What changed` | One or two plain sentences on what this meeting changed, with `[S#]` citations | Passages retrieved from the EPAR, variation and NICE pages |
| `Summary sources` | Which documents the retriever supplied for that summary | Retrieval metadata |

### Regulatory Dates

| Feature | Description | Source |
|---|---|---|
| `Initial Approval` | Initial approval or extension of indication | CHMP Meeting Highlights |
| `CHMP Opinion Date` | Last day of CHMP meeting | CHMP Meeting Highlights |
| `Decision date` | European Commission decision date | EMA medicine list |
| `EMA date for extension` | Date of most recent extension (LLM-extracted) | Procedure steps PDF |
| `title` | Title of CHMP Meeting Highlights news | CHMP Meeting Highlights |
| `date` | Date of CHMP Meeting Highlights news | CHMP Meeting Highlights |

### NICE Comparison

| Feature | Description | Source |
|---|---|---|
| `Search Result in NICE` | Whether medicine appears in NICE search | NICE search page |
| `NICE_url` | NICE search URL for the medicine | Generated from INN |
| `Full Indication Similarity` | Similarity between EMA full indication and NICE text (LLM-scored) | NICE page + EMA |
| `New Indication HTML Similarity` | Similarity between new indication (HTML) and NICE text (LLM-scored) | NICE page + EMA |
| `New Indication PDF Similarity` | Similarity between new indication (PDF) and NICE text (LLM-scored) | NICE page + EMA |

---

## Project Structure

```
├── notebooks/
│   ├── EMA_data_scraping.ipynb      # Main notebook (Colab or local Jupyter)
│   └── (Llama3_1)Experiment_...ipynb  # First RAG attempt: Ollama/HF + LangChain + Chroma
├── scripts/
│   ├── config.py                    # HTTP headers, timeouts, OpenAI client
│   ├── llm.py                       # Single model entry point: retries, size guard
│   ├── http_utils.py                # Fetching + trimming pages before the LLM sees them
│   ├── rag.py                       # Chunking, embedding and per-medicine retrieval
│   ├── summarise.py                 # The retrieval-grounded "What changed" summary
│   ├── ema_meeting_highlights.py    # Finds the latest CHMP news item and its links
│   ├── extractors.py                # All six extraction/comparison prompts
│   ├── batch.py                     # Runs one extractor over a list of URLs
│   ├── build_dataset.py             # End-to-end assembly of the dataset
│   ├── scrape_data_fromMH_with_LLM.py  # One record per medicine
│   ├── scrape_data_fromEPAR.py      # Therapy class / area from the EPAR page
│   ├── scrape_data_fromNICE.py      # NICE search hit check
│   ├── scrape_data_fromSHEET.py     # Medicine list lookup
│   ├── scrape_therapy_area.py       # Therapy area lookup
│   ├── compare_nice_and_indication.py
│   ├── text_fromNICE.py
│   ├── extract_text_from_pdf.py
│   ├── download_procedural_pdf.py   # Finds and fetches the procedural steps PDF
│   └── get_chmp_opinion_date.py
├── tests/
│   ├── fetch_fixtures.py            # Re-downloads the saved pages
│   ├── fixtures/                    # Saved EMA/NICE pages (gzipped)
│   └── test_*.py                    # Offline regression tests
├── evaluation/
│   ├── metrics.py                   # ROUGE + exact match + classification + summary metrics
│   ├── grounding.py                 # Label-free: is every answer really on the page?
│   │                                #   and: did retrieval find what EMA marked up?
│   ├── cross_check.py               # Label-free: does it match EMA's own exports?
│   ├── evaluate.py                  # Scores a run against a gold file
│   ├── gold_template.csv            # Shape of the hand-checked reference file
│   └── gold_chmp_2026_07.csv        # Gold set for the July 2026 meeting (16 medicines)
├── data/
│   ├── medicines_output_medicines_en.xlsx   # EMA medicine list
│   └── therapy_area.xlsx                    # Therapy area lookup table
└── results/
    └── final_EMA_dataset.xlsx       # Output dataset
```

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then add your OpenAI key
```

The pipeline reads `OPENAI_API_KEY` from the environment. In Colab, store it as a
notebook secret; the setup cell copies it into `os.environ`.

`requirements.txt` includes the four retrieval packages
(`langchain-text-splitters`, `langchain-openai`, `langchain-chroma`, `chromadb`).
They are only used by the summary step — skip them and everything else still
imports and runs, and the retrieval tests skip themselves.

The EMA medicines table is downloaded from
[EMA's medicine data page](https://www.ema.europa.eu/en/medicines/download-medicine-data)
(now published as `medicines-output-medicines-report_en.xlsx`). The real header row
of that export sits on row 9, hence `header=8`.

---

## Retrieval

Every indication column is an **extraction** — the answer is on the page, word
for word — so the trimmed page goes straight into the prompt and nothing is
searched.

`What changed` is the exception. It reads across a whole EPAR, the variation
diff and the NICE result, which does not fit: an untrimmed Keytruda EPAR is
~200k tokens, so `llm.truncate` starts cutting and whatever it cuts is gone
silently. That step retrieves instead:

```
pages ─▶ to_markers ─▶ RecursiveCharacterTextSplitter ─▶ OpenAIEmbeddings ─▶ Chroma
                            1200 / 200               text-embedding-3-small      │
     GPT-4o mini ◀── numbered, citable context ◀── top-4, filtered by product ───┘
```

Two things make it work on regulatory pages, both learned from the failed first
attempt in [`notebooks/(Llama3_1)Experiment_...ipynb`](notebooks/) (Ollama +
Hugging Face), whose own note says why it was dropped: *"All text on web pages is
extracted as plain text and stored as vectors, ignoring bold or strikethrough
formatting."*

- **The markup is the signal.** `rag.to_markers` rewrites `<strong>`/`<s>` into
  `[ADDED]`/`[REMOVED]` before chunking, so EMA's diff survives embedding and
  retrieval. The markers are chunk separators too, so a boundary never lands
  inside a span.
- **Search is scoped to one medicine**, on product name in the chunk metadata.
  Without it, medicines from the same meeting share too much vocabulary and the
  wrong drug's indication comes back.

The marked-up fragments are pinned into the prompt whatever the search returns.
Passages are numbered `[S1]`, `[S2]`, … and the prompt requires a citation per
sentence — an uncited sentence is one the model did not get from the sources.

Only this step needs the retrieval packages from [Setup](#setup).

---

## Checking a run

Three layers; only the last needs labels.

**1. Regression tests.** The pipeline breaks when EMA changes their markup, not
when the model has a bad day. Saved pages in `tests/fixtures/` pin the structure
the scrapers depend on, so a redesign fails a test instead of producing an empty
file.

```bash
pytest tests/                       # 80 tests, offline, ~3s
python tests/fetch_fixtures.py      # refresh the saved pages
```

**2. Grounding and cross-checks — no labels.** `cross_check.py` compares the
dataset with EMA's own published exports: the post-authorisation table validates
which medicines had an extension and when, the medicines table validates the
Commission decision dates. `grounding.py` checks that every extracted phrase is
really on the page, and scores the bold/strikethrough columns against the markup
itself.

```bash
python evaluation/cross_check.py results/final_EMA_dataset.xlsx
```

The summary needs its own version of this, being the one output allowed to
rephrase. `grounding.check_retrieval` and `check_summaries` report:

- **Retrieval recall** — of the spans EMA marked up, how many the search found.
- **`supported_fraction`** — how much of the summary's vocabulary is in the
  passages it was given. Catches what ROUGE cannot: a fluent sentence about a
  trial result no source mentioned.
- **`citation_rate`** — sentences citing a passage that was really retrieved.

**3. Scored against a gold file — needs labels.** Four kinds of answer, four
metrics:

| Output | Metric |
|---|---|
| The four indication fields | **Exact match**, with ROUGE-1/2/L and token precision/recall alongside |
| `EMA date for extension` | **Exact match**, format-tolerant |
| The three similarity fields | **Accuracy, precision, recall, F1, kappa** |
| `What changed` | **ROUGE-1/2/L** against a reference summary, read next to the label-free numbers above |

ROUGE is never the headline. An answer that flips a negation ("is **not**
indicated … HER2-**negative**") still scores ROUGE-L ≈ 0.91 against the correct
text, so exact match leads for the extractions, and the summary — the one output
with no single correct wording — is read beside `supported_fraction`.

```bash
python evaluation/evaluate.py results/final_EMA_dataset.xlsx evaluation/gold_chmp_2026_07.csv
```

`gold_chmp_2026_07.csv` covers the 16 medicines of the July 2026 meeting:
`What changed` for each, and the two diff columns off the markup; see
limitation 1. For another meeting, copy `gold_template.csv` —
`grounding.marked_up_fragments` gives you those two columns, the rest is
annotation.

The report prints `labelled=` beside `n=`. A blank reference against a blank
prediction scores 1.0, correctly, but an unannotated column is all blanks too and
would otherwise look perfect off no evidence.

---

## Known limitations and future work

**1. The gold set here is a stand-in.** The reference summaries this was
evaluated against are internal material and cannot go in a personal repository,
so neither they nor any number from them is here.
`evaluation/gold_chmp_2026_07.csv` is a substitute built from the public EMA
pages and checked by hand against each medicine's EPAR overview or variation
diff — a worked example of the evaluation, not its result. `Full Indication`,
the similarity columns and the PDF columns are blank in it.

To get a number out of *this repository*, annotate ~30–50 medicines (two to
three meetings). Rows are not `n`: only extensions have a variation page, so the
diff columns get about half the rows — `labelled=7` and `labelled=3` on the
committed set. At an observed 90%, a Wilson 95% interval is ±0.15 at n=16 and
±0.11 at n=30. Annotate for spread, and include the medicines whose diff is many
small fragments — those are what the summary step exists for.

Note also that any NICE-similarity figure from before commit `bfdadd4` is wrong:
`N/A` was scored as an explicit "No" rather than excluded.

**2. `supported_fraction` is lexical, not semantic.** It is wrong in both
directions — a correct paraphrase scores low, a false claim assembled from words
that are in the sources scores high. An entailment check is the version this
should have been.

**3. The PDF columns cover extensions only.** `New indication PDF` and `EMA
date for extension` come from EMA's procedural steps PDF, which the run now
downloads itself from the link on each EPAR page. Only authorised medicines have
one, so a first authorisation leaves both columns `N/A` — there is no
post-authorisation history to read. The extraction is also the weakest step in
the pipeline: on the committed October 2024 run the model answered
`I don't know.` for two of five PDFs, because the prompt keys off one exact
table header (`Commission Decision Issued2 / amended`) and the layout of these
documents varies.

**4. The NICE side is shallow.** The similarity columns compare against the NICE
*search results page*, not the guidance document — "does a NICE result look
related", not "NICE has appraised this indication".

**5. Retrieval was never tuned.** Chunk size 1200, overlap 200, top-4, one query
string: all first guesses from the original notebook. `check_retrieval` exists to
measure the effect of changing them but has only run against a stub embedder.
`add_summaries` does not expose `k`, the index is rebuilt in memory every run
though `build_store(persist_dir=...)` supports persistence, and a hybrid search
on the `[ADDED]`/`[REMOVED]` markers is the obvious next thing to try.

**6. One meeting at a time.** Only the most recent Meeting Highlights is ever
read, so no trend analysis — EMA-to-NICE lag, variation by therapy area — is
possible without a backfill.

---

## Objectives

Build a consistent database of regulatory and HTA guidance on medicines, by
automating the collection step by step from EMA and NICE.

## AI Utilization

- **GPT-4o mini** — chosen over Llama 3.1 for speed. Two jobs: extracting
  structured fields verbatim from HTML, PDFs and NICE pages, and writing the
  `What changed` summary from retrieved passages.
- **`text-embedding-3-small`** over EMA and NICE pages, chunked with LangChain
  and indexed in Chroma. Used by the summary step only.
- **Evaluation** — exact match for the extractions, ROUGE-1/2/L for the
  summaries, plus three checks that need no labels: grounding, retrieval recall
  against EMA's own markup, and supported fraction.
- **Output** — Excel/CSV, 25 columns per medicine, 27 with the summaries.
