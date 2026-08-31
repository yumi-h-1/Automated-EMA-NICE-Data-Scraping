"""Chunking, embedding and retrieval over the EMA and NICE pages.

Every indication column in this pipeline is an *extraction*: the answer is
already on the page, word for word, and the prompt only has to copy it. Those
need no retrieval — `http_utils` narrows the page to the relevant section and
the whole thing goes into the prompt.

The summary column is the exception. It has to read across a whole EPAR, the
variation diff and the NICE result and say in a sentence what a meeting
changed, and that does not fit: an untrimmed Keytruda EPAR is ~200k tokens, so
`llm.truncate` starts cutting and whatever it cuts is silently gone. Retrieval
replaces that blind truncation with a choice — the model is given the passages
that answer the question, and the summary cites which ones it used.

Two details make this work on regulatory pages. Both come out of the first
attempt at it, in `notebooks/(Llama3_1)Experiment_Ollama_+_Langchain__etc.ipynb`,
which was abandoned because it could not read a variation page at all:

  1. **The markup is the signal.** EMA marks a newly added indication in bold
     and a removed one in strikethrough. A plain-text loader throws that away,
     and once it is gone no amount of retrieval can tell an added indication
     from the paragraph around it — which is exactly what went wrong the first
     time. `to_markers` rewrites <strong> and <s> into literal [ADDED] and
     [REMOVED] markers *before* chunking, so the distinction survives embedding,
     retrieval and the prompt.
  2. **Retrieval is scoped to one medicine.** Chunks carry the product name in
     their metadata and every search filters on it. Without that filter,
     medicines recommended at the same meeting share far too much vocabulary —
     "advanced non-small cell lung cancer" retrieves the wrong drug.

The marked-up fragments are also pinned into the prompt regardless of what the
search returns. They are short, and they are the one thing a summary must not
miss.

These are optional dependencies; everything else in the pipeline runs without
them:

    pip install langchain-text-splitters langchain-openai langchain-chroma chromadb
"""

import os
import re

from bs4 import BeautifulSoup

# Regulatory indications run long — one sentence naming disease, line of therapy
# and biomarker is easily 400 characters — so a chunk has to be big enough to
# hold a whole one, and overlap enough that a bad split leaves both halves
# intact somewhere.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

# Four ~1200-character chunks is roughly 1.5k tokens: enough for the indication
# and its context, small enough that the model cannot pad the summary out with
# unrelated material.
TOP_K = 4

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')

_INSTALL_HINT = (
    'Retrieval needs the optional dependencies. Install them with:\n'
    '    pip install langchain-text-splitters langchain-openai langchain-chroma chromadb'
)

# Tags EMA uses to mark an indication change, and the marker each becomes.
_MARKED_UP = {
    'strong': 'ADDED',
    'b': 'ADDED',
    's': 'REMOVED',
    'del': 'REMOVED',
    'strike': 'REMOVED',
}

# Bold text EMA repeats on every page, which has nothing to do with any
# indication. The extraction prompts are told to ignore it; here it is emitted
# as ordinary text so it cannot be retrieved as though it were a change.
BOILERPLATE = ('First published:', 'This page was last updated on',
               'European Medicines Agency', 'Share')

_WHITESPACE = re.compile(r'\s+')
_MARKER = re.compile(r'\[(ADDED|REMOVED)\](.*?)\[/\1\]', re.DOTALL)


# --- turning pages into retrievable text ------------------------------------

def to_markers(html):
    """Flatten markup to text, keeping the added/removed distinction.

    <strong>foo</strong> becomes [ADDED]foo[/ADDED] and <s>bar</s> becomes
    [REMOVED]bar[/REMOVED].
    """
    if not html:
        return ''

    doc = BeautifulSoup(str(html), 'html.parser')
    for tag_name, marker in _MARKED_UP.items():
        for element in doc.find_all(tag_name):
            text = element.get_text(' ', strip=True)
            if not text:
                element.decompose()
                continue
            if any(text.startswith(prefix) for prefix in BOILERPLATE):
                element.replace_with(text)
            else:
                element.replace_with(f'[{marker}]{text}[/{marker}]')

    return _WHITESPACE.sub(' ', doc.get_text(' ', strip=True)).strip()


def documents_from_dataset(dataset, pages, nice_texts=None):
    """Every page behind the dataset as a {text, metadata} record.

    `pages` is the {url: trimmed HTML} dict `build_ema_dataset` fills in, so
    nothing is fetched twice. `nice_texts` is the {url: text} dict from
    `text_fromNICE`, which is gathered later in the run and so arrives
    separately.
    """
    nice_texts = nice_texts or {}
    documents = []

    for _, row in dataset.iterrows():
        name = row['Product Name']

        def add(text, source, url):
            if text and str(text).strip():
                documents.append({
                    'text': text,
                    'metadata': {'product': name, 'source': source, 'url': url or ''},
                })

        add(to_markers(pages.get(row.get('epar_url'))),
            'EPAR indication', row.get('epar_url'))

        variation_urls = [u.strip() for u in str(row.get('variation_url', '')).split(',')
                          if u.strip() and u.strip() != 'N/A']
        for index, url in enumerate(variation_urls, start=1):
            label = 'variation' if index == 1 else f'variation {index}'
            add(to_markers(pages.get(url)), label, url)

        # NICE search results are already plain text, with no markup to keep.
        nice_url = row.get('NICE_url')
        if nice_url and nice_url != 'N/A':
            add(nice_texts.get(nice_url), 'NICE', nice_url)

    return documents


def split_documents(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    """Chunk each document, carrying its metadata onto every chunk."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as e:  # pragma: no cover - dependency guard
        raise ImportError(_INSTALL_HINT) from e

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # Break between indications first, then sentences, then words. The
        # markers are separators too, so a chunk boundary lands before a
        # marked-up span rather than inside it.
        separators=['\n\n', '\n', '[ADDED]', '[REMOVED]', '. ', ' ', ''],
    )

    chunks = []
    for document in documents:
        for position, piece in enumerate(splitter.split_text(document['text'])):
            chunks.append({
                'text': piece,
                'metadata': {**document['metadata'], 'chunk': position},
            })
    return chunks


# --- the vector store --------------------------------------------------------

def build_store(documents, persist_dir=None, embeddings=None, collection='ema-nice'):
    """Chunk, embed and index a set of documents in Chroma.

    `embeddings` is injectable so the tests can index without an API key, and so
    a local embedding model can be swapped in without touching anything else.
    """
    # Check the input before touching any dependency. A run with nothing to
    # index should fail on that, not on a missing package or API key that would
    # have made no difference to the outcome.
    if not documents:
        raise ValueError('there is no page text to index')

    try:
        from langchain_chroma import Chroma
    except ImportError as e:  # pragma: no cover - dependency guard
        raise ImportError(_INSTALL_HINT) from e

    chunks = split_documents(documents)
    if not chunks:
        raise ValueError('there is no page text to index')

    if embeddings is None:
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as e:  # pragma: no cover - dependency guard
            raise ImportError(_INSTALL_HINT) from e
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    store = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=str(persist_dir) if persist_dir else None,
    )
    store.add_texts(
        texts=[chunk['text'] for chunk in chunks],
        metadatas=[chunk['metadata'] for chunk in chunks],
    )
    return store


# What a summary needs to know, phrased as the sentence we hope to retrieve
# rather than as keywords — the whole string is what gets embedded.
SUMMARY_QUERY = (
    'therapeutic indication of the medicine, the patient population, and the '
    'indication that was newly added or removed at this meeting'
)


class Retriever:
    """Per-medicine search over one meeting's pages."""

    def __init__(self, store, k=TOP_K):
        self.store = store
        self.k = k

    def search(self, product_name, query=SUMMARY_QUERY, k=None):
        """The k best chunks for one medicine, most relevant first."""
        results = self.store.similarity_search(
            query, k=k or self.k, filter={'product': product_name},
        )
        return [{'text': document.page_content, 'metadata': document.metadata}
                for document in results]


# --- assembling the prompt context ------------------------------------------

def marked_spans(chunks, marker):
    """Every [ADDED] or [REMOVED] span inside a set of retrieved chunks."""
    spans = []
    for chunk in chunks:
        for found, text in _MARKER.findall(chunk['text']):
            if found == marker and text.strip() and text.strip() not in spans:
                spans.append(text.strip())
    return spans


def format_context(chunks):
    """Retrieved chunks as a numbered, citable block.

    Numbering is what lets the summary prompt demand a citation per sentence:
    an uncitable sentence is one the model did not get from the sources.
    """
    lines = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk['metadata']
        origin = metadata.get('source', 'source')
        url = metadata.get('url')
        heading = f'[S{index}] {origin}' + (f' - {url}' if url else '')
        lines.append(f'{heading}\n{chunk["text"].strip()}')
    return '\n\n'.join(lines)


def sources_used(chunks):
    """The distinct documents behind a set of chunks, for the dataset column."""
    seen = []
    for chunk in chunks:
        source = chunk['metadata'].get('source', 'source')
        if source not in seen:
            seen.append(source)
    return ', '.join(seen)
