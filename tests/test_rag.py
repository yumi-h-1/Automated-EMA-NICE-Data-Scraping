"""Retrieval tests.

Everything that needs no API key — turning markup into text, building the
documents, reading the markers back out — is tested directly, including against
the saved Enhertu variation page. The two tests that need the optional
LangChain/Chroma dependencies skip themselves when those are missing.
"""

import pandas as pd
import pytest

import rag

VARIATION_HTML = """
<div>
  <p><strong>First published: 21 July 2026</strong></p>
  <p>Keytruda is indicated <strong>in combination with chemotherapy for the
  first-line treatment of adults with advanced gastric cancer</strong>, and
  <s>as monotherapy in previously treated adults</s>.</p>
</div>
"""

EPAR_HTML = '<p>Keytruda is indicated for advanced melanoma in adults.</p>'

DATASET = pd.DataFrame([
    {'Product Name': 'keytruda',
     'epar_url': 'https://ema.example/EPAR/keytruda',
     'variation_url': 'https://ema.example/variation/keytruda',
     'NICE_url': 'https://nice.example/search?q=pembrolizumab'},
    {'Product Name': 'jivi',
     'epar_url': 'https://ema.example/EPAR/jivi',
     'variation_url': 'N/A',
     'NICE_url': 'N/A'},
])

PAGES = {
    'https://ema.example/EPAR/keytruda': EPAR_HTML,
    'https://ema.example/variation/keytruda': VARIATION_HTML,
    'https://ema.example/EPAR/jivi': '<p>Jivi is indicated for haemophilia A.</p>',
}

NICE_TEXTS = {'https://nice.example/search?q=pembrolizumab':
              'Pembrolizumab for treating advanced gastric cancer.'}


class TestToMarkers:
    def test_bold_becomes_an_added_marker(self):
        text = rag.to_markers(VARIATION_HTML)
        assert '[ADDED]in combination with chemotherapy' in text
        assert text.count('[/ADDED]') == 1

    def test_strikethrough_becomes_a_removed_marker(self):
        assert '[REMOVED]as monotherapy in previously treated adults[/REMOVED]' \
            in rag.to_markers(VARIATION_HTML)

    def test_boilerplate_bold_is_not_marked_up(self):
        """EMA bolds the publication banner on every page; it is not a change."""
        text = rag.to_markers(VARIATION_HTML)
        assert 'First published: 21 July 2026' in text
        assert '[ADDED]First published' not in text

    def test_plain_text_survives_unchanged(self):
        assert rag.to_markers(EPAR_HTML) == 'Keytruda is indicated for advanced melanoma in adults.'

    def test_empty_input(self):
        assert rag.to_markers(None) == ''
        assert rag.to_markers('') == ''

    def test_a_real_variation_page_keeps_its_markup(self, soup):
        """The saved Enhertu page is the case the whole design exists for."""
        from http_utils import condense_html

        text = rag.to_markers(condense_html(soup('variation_enhertu')))
        assert '[ADDED]' in text, 'the added indication was lost before chunking'
        assert 'First published' in text and '[ADDED]First published' not in text


class TestDocuments:
    def test_one_document_per_page(self):
        documents = rag.documents_from_dataset(DATASET, PAGES, NICE_TEXTS)
        assert [(d['metadata']['product'], d['metadata']['source']) for d in documents] == [
            ('keytruda', 'EPAR indication'),
            ('keytruda', 'variation'),
            ('keytruda', 'NICE'),
            ('jivi', 'EPAR indication'),
        ]

    def test_pages_that_were_never_fetched_are_skipped(self):
        """Jivi has no variation page and no NICE hit — neither is indexed."""
        documents = rag.documents_from_dataset(DATASET, PAGES, NICE_TEXTS)
        assert [d for d in documents if d['metadata']['product'] == 'jivi'] == documents[3:]

    def test_documents_carry_their_url(self):
        documents = rag.documents_from_dataset(DATASET, PAGES, NICE_TEXTS)
        variation = next(d for d in documents if d['metadata']['source'] == 'variation')
        assert variation['metadata']['url'] == 'https://ema.example/variation/keytruda'

    def test_nice_text_is_optional(self):
        documents = rag.documents_from_dataset(DATASET, PAGES)
        assert not [d for d in documents if d['metadata']['source'] == 'NICE']


class TestReadingMarkersBack:
    def test_added_and_removed_are_kept_apart(self):
        chunks = [{'text': rag.to_markers(VARIATION_HTML), 'metadata': {}}]
        assert rag.marked_spans(chunks, 'ADDED')[0].startswith('in combination with chemotherapy')
        assert rag.marked_spans(chunks, 'REMOVED') == \
            ['as monotherapy in previously treated adults']

    def test_duplicates_across_chunks_are_collapsed(self):
        chunk = {'text': '[ADDED]same text[/ADDED]', 'metadata': {}}
        assert rag.marked_spans([chunk, dict(chunk)], 'ADDED') == ['same text']


class TestContext:
    CHUNKS = [
        {'text': 'first passage', 'metadata': {'source': 'EPAR indication',
                                               'url': 'https://ema.example/k'}},
        {'text': 'second passage', 'metadata': {'source': 'variation', 'url': ''}},
        {'text': 'third passage', 'metadata': {'source': 'variation', 'url': ''}},
    ]

    def test_passages_are_numbered_for_citation(self):
        context = rag.format_context(self.CHUNKS)
        assert '[S1] EPAR indication - https://ema.example/k' in context
        assert '[S2] variation' in context and '[S3] variation' in context

    def test_sources_are_listed_once_each(self):
        assert rag.sources_used(self.CHUNKS) == 'EPAR indication, variation'

    def test_no_chunks(self):
        assert rag.format_context([]) == ''
        assert rag.sources_used([]) == ''


class TestSplitting:
    def test_metadata_is_carried_onto_every_chunk(self):
        pytest.importorskip('langchain_text_splitters')
        documents = [{'text': 'sentence. ' * 400,
                      'metadata': {'product': 'keytruda', 'source': 'EPAR indication',
                                   'url': 'https://ema.example/k'}}]
        chunks = rag.split_documents(documents)
        assert len(chunks) > 1
        assert all(chunk['metadata']['product'] == 'keytruda' for chunk in chunks)
        assert [chunk['metadata']['chunk'] for chunk in chunks] == list(range(len(chunks)))

    def test_a_marked_up_span_is_not_split_down_the_middle(self):
        """The markers are separators, so a boundary lands before one, not inside."""
        pytest.importorskip('langchain_text_splitters')
        filler = 'Background text about the medicine. ' * 40
        text = filler + '[ADDED]the newly added indication[/ADDED]' + filler
        chunks = rag.split_documents([{'text': text, 'metadata': {'product': 'x'}}],
                                     chunk_size=400, chunk_overlap=50)
        holding = [c['text'] for c in chunks if 'newly added indication' in c['text']]
        assert holding and any('[ADDED]' in chunk for chunk in holding)


class TestStore:
    def test_retrieval_never_crosses_medicines(self):
        pytest.importorskip('langchain_chroma')
        from langchain_core.embeddings import FakeEmbeddings

        documents = rag.documents_from_dataset(DATASET, PAGES, NICE_TEXTS)
        store = rag.build_store(documents, embeddings=FakeEmbeddings(size=64))
        retriever = rag.Retriever(store, k=4)

        for name in ('keytruda', 'jivi'):
            results = retriever.search(name)
            assert results
            assert all(chunk['metadata']['product'] == name for chunk in results)

    def test_nothing_to_index_is_an_error_not_an_empty_store(self):
        """And it fails on that, not on a missing API key."""
        with pytest.raises(ValueError):
            rag.build_store([])
