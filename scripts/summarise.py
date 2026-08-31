"""The plain-English summary of what a CHMP meeting changed, grounded in retrieval.

EMA marks an indication change as a character-level diff, so the raw extracted
fields read as fragments — "A", "-based regimen", "an". They are accurate and
almost unreadable. This step turns them back into a sentence, using only the
passages `rag` retrieves for that medicine, and makes the model cite which
passage each sentence came from.

    from summarise import add_summaries
    add_summaries(ema_data_df, pages, nice_text_dict)

Adds two columns: 'What changed' and 'Summary sources'.
"""

from llm import SUMMARISER_SYSTEM, ask_model, truncate
from rag import (Retriever, build_store, documents_from_dataset, format_context,
                 marked_spans, sources_used, to_markers)


def query_model_for_change_summary(product_name, recommendation, context, added, removed):
    """One or two sentences saying what this meeting changed, from the sources only."""
    added_text = '; '.join(added) if added else '(none)'
    removed_text = '; '.join(removed) if removed else '(none)'

    prompt = f"""A medicine received a positive CHMP opinion. Using ONLY the numbered sources
    below, write one or two plain sentences saying what changed.

    Medicine: {product_name}
    Kind of recommendation: {recommendation}

    Sources retrieved from the EMA and NICE pages:
    \"\"\"
    {truncate(context, 60_000)}
    \"\"\"

    Text EMA marked as ADDED: \"\"\"{truncate(added_text, 8_000)}\"\"\"
    Text EMA marked as REMOVED: \"\"\"{truncate(removed_text, 8_000)}\"\"\"

    The added and removed fragments come from a character-level diff, so they may be
    sentence fragments. Read them together with the sources to work out the change.

    Rules:
    - Use only what the sources state. Do not add clinical background, trial results,
      comparisons, or anything about other medicines.
    - Cite the source for each sentence as [S1], [S2] and so on, at the end of the sentence.
    - Name the disease, the patient population and the line of therapy only if the
      sources give them.
    - If it is a first authorisation, say what the medicine is approved to treat.
    - If the sources do not support any statement, write exactly 'Not stated'.
    - No preamble. Just the sentences."""
    return ask_model(prompt, system=SUMMARISER_SYSTEM)


def diff_fragments(row, pages):
    """The text EMA marked as added and removed on a medicine's variation pages.

    Taken from the whole page rather than from the retrieved chunks: these are
    short and they are the one thing the summary must not miss, so they are
    pinned into the prompt regardless of what the search returned.
    """
    added, removed = [], []
    for url in str(row.get('variation_url', '')).split(','):
        url = url.strip()
        if not url or url == 'N/A' or url not in pages:
            continue
        document = [{'text': to_markers(pages[url]), 'metadata': {}}]
        for span in marked_spans(document, 'ADDED'):
            if span not in added:
                added.append(span)
        for span in marked_spans(document, 'REMOVED'):
            if span not in removed:
                removed.append(span)
    return added, removed


def add_summaries(dataset, pages, nice_texts=None, retriever=None,
                  persist_dir=None, embeddings=None, retrieval_log=None):
    """Add 'What changed' and 'Summary sources' to a built dataset.

    Builds the index from the pages the run already fetched, so nothing is
    downloaded twice. Pass `retrieval_log` a dict to keep the retrieved chunks
    for scoring afterwards; see `evaluation/grounding.py`.
    """
    if retriever is None:
        documents = documents_from_dataset(dataset, pages, nice_texts)
        print(f'Indexing {len(documents)} pages for retrieval...')
        store = build_store(documents, persist_dir=persist_dir, embeddings=embeddings)
        retriever = Retriever(store)

    summaries, all_sources = [], []

    for _, row in dataset.iterrows():
        name = row['Product Name']
        chunks = retriever.search(name)
        if retrieval_log is not None:
            retrieval_log[name] = chunks

        if not chunks:
            # Every page for this medicine was empty or failed to fetch.
            # Writing a summary anyway would hide that, so say so instead.
            summaries.append('N/A')
            all_sources.append('no passages retrieved')
            continue

        added, removed = diff_fragments(row, pages)
        summaries.append(query_model_for_change_summary(
            name, row.get('Initial Approval', 'N/A'),
            format_context(chunks), added, removed,
        ))
        all_sources.append(sources_used(chunks))
        print(f'  summary: {name}')

    dataset['What changed'] = summaries
    dataset['Summary sources'] = all_sources
    return dataset
