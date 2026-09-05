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

## AI Utilization

- **GPT-4o mini** — It does two jobs: extracting structured fields from EMA pages, PDFs and NICE pages, and writing the
  `What changed` summary.
- **`text-embedding-3-small`** - This chunks EMA and NICE pages with LangChain
  and indexed in Chroma. Used by the summary step.
- **Evaluation** — Three types: exact match for the extractions, binary classification, ROUGE-1/2/L for the
  summaries.
- **Output** — An Excel/CSV file.


## Pipeline

```mermaid
flowchart LR
    N["EMA news\nlisting"] --> MH["CHMP Meeting\nHighlights"]
    MH --> FET["Fetch EPAR, variation\nand NICE pages"]
    MH --> PDF["Download procedural\nsteps PDF"]

    FET --> TRIM["BeautifulSoup\nstrip noise, narrow to\nthe indication section"]
    TRIM --> PG["pages\ntrimmed markup,\nstrong and s preserved"]

    PG --> BS["BeautifulSoup reads\nINN, MA holder, ATC,\ndates, NICE hit"]
    PG --> EXT["GPT-4o mini\nindication columns"]
    PG --> IDX["to_markers, chunk 1200/200,\nembed, Chroma"]
    PDF --> PEX["pypdf then GPT-4o mini\nPDF columns"]

    IDX --> RET["Retrieve top-4,\nfiltered by product"]
    RET --> SUM["GPT-4o mini summary\ncited S1..S4"]

    BS --> OUT["Excel or CSV file\n25 columns + 2"]
    EXT --> OUT
    PEX --> OUT
    SUM --> OUT
```

Three things in that diagram are easy to get backwards:

- **BeautifulSoup and the model are not alternatives.** Trimming runs *first* and
  produces the input the model reads — the raw Keytruda EPAR is 132,209 tokens,
  past the 128k window, and 16,761 after narrowing. What splits the work after
  that is the shape of the data, not what either tool is capable of: fields with
  a fixed position in the DOM (`dt`/`dd` pairs, the ATC code, links, the NICE
  result title) are read by BeautifulSoup, and free prose that no selector can
  address (the indication sentence, the diff, the PDF table) goes to the model.
- **The vector store is fed from `pages`, not from the extracted columns.** The
  summary re-reads the trimmed pages independently, so an extraction error
  cannot propagate into it, and `grounding.py` can score the two separately.
- **The PDF never enters the vector store.** Its text goes straight into the two
  PDF prompts and stops there.

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
├── run_pipeline.py                  # Terminal entry point; same steps as the notebook
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

## Set Up

Two ways in, depending on who is running it. Both do the same work in the same
order, and both write `results/final_EMA_dataset.xlsx`.

### In the browser — no install

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/yumi-h-1/Automated-EMA-NICE-Data-Scraping/blob/main/notebooks/EMA_data_scraping.ipynb)

Open `notebooks/EMA_data_scraping.ipynb` in Colab and run the cells. The setup
cell clones this repository and installs everything, so nothing has to be
installed locally. Store your key as a Colab secret named `OPENAI_API_KEY`; the
setup cell copies it into `os.environ`.

This is the path to send someone who just wants the spreadsheet.

### From the terminal

```bash
git clone https://github.com/yumi-h-1/Automated-EMA-NICE-Data-Scraping
cd Automated-EMA-NICE-Data-Scraping

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # add your OpenAI key; config.py loads this file
python run_pipeline.py
```

`run_pipeline.py` calls the same functions the notebook calls, in the same
order — the notebook is for reading the result, the script is for reproducing
it. A full run takes roughly two minutes.

```bash
python run_pipeline.py --no-summaries       # skip retrieval; no heavy dependencies needed
python run_pipeline.py --output-dir /tmp/x  # write somewhere other than results/
python run_pipeline.py --no-refresh         # keep the cached EMA medicines table
python run_pipeline.py --help
```

It exits non-zero if a column that should never be empty came back `N/A`, so it
can be run on a schedule and its exit status believed.

### Dependencies

`OPENAI_API_KEY` is required for the extraction, comparison and summary.

The EMA medicines table is downloaded on every run from
[EMA's medicine data page](https://www.ema.europa.eu/en/medicines/download-medicine-data)
(published as `medicines-output-medicines-report_en.xlsx`). It changes weekly, and
a stale copy produces out-of-date Commission decision dates rather than an error.
The real header row of that export sits on row 9, hence `header=8`.

The procedural steps PDFs behind `New indication PDF` and `EMA date for extension`
are downloaded by the run itself from the link on each medicine's EPAR page. 
If you place a PDF file directly in `data/ema_pdf/`, that file will be used instead.

---

## Retrieval

Every indication column is an **extraction** — the answer is on the page, word
for word — so the trimmed page goes straight into the prompt and nothing is
searched.

`What changed` is the exception. It reads across a whole EPAR, the variation
diff and the NICE result at once. The raw Keytruda EPAR page measures 132,209
tokens, over the model's 128k window, which is why every page is narrowed before
it reaches a prompt at all. That step retrieves instead:

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
