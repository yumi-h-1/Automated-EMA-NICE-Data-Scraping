"""The summarisation step, with the model replaced by a recorder.

What these check is the wiring: that the summary is written from the retrieved
passages rather than from anything else, that the diff fragments reach the
prompt whether or not the search found them, and that a medicine with nothing
indexed is reported as such instead of getting a summary invented for it.
"""

import pandas as pd
import pytest

import summarise

VARIATION_HTML = """
<p>Keytruda is indicated <strong>in combination with chemotherapy for the
first-line treatment of adults with advanced gastric cancer</strong>, and
<s>as monotherapy in previously treated adults</s>.</p>
"""

DATASET = pd.DataFrame([{
    'Product Name': 'keytruda',
    'Initial Approval': 'Extension',
    'epar_url': 'https://ema.example/EPAR/keytruda',
    'variation_url': 'https://ema.example/variation/keytruda',
    'NICE_url': 'N/A',
}])

PAGES = {
    'https://ema.example/EPAR/keytruda': '<p>Keytruda is indicated for melanoma.</p>',
    'https://ema.example/variation/keytruda': VARIATION_HTML,
}

CHUNKS = [
    {'text': 'Keytruda is indicated [ADDED]in combination with chemotherapy[/ADDED].',
     'metadata': {'product': 'keytruda', 'source': 'variation',
                  'url': 'https://ema.example/variation/keytruda'}},
    {'text': 'Pembrolizumab for advanced gastric cancer.',
     'metadata': {'product': 'keytruda', 'source': 'NICE',
                  'url': 'https://nice.example/k'}},
]


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.asked_for = []

    def search(self, product_name, *args, **kwargs):
        self.asked_for.append(product_name)
        return self.chunks


@pytest.fixture
def prompts(monkeypatch):
    """Record every prompt instead of calling the API."""
    recorded = []

    def fake(prompt, system=None, attempts=3, temperature=0):
        recorded.append({'prompt': prompt, 'system': system})
        return 'Keytruda is now approved with chemotherapy for gastric cancer. [S1]'

    monkeypatch.setattr(summarise, 'ask_model', fake)
    return recorded


class TestDiffFragments:
    def test_added_and_removed_are_read_off_the_page(self):
        added, removed = summarise.diff_fragments(DATASET.iloc[0], PAGES)
        assert added[0].startswith('in combination with chemotherapy')
        assert removed == ['as monotherapy in previously treated adults']

    def test_a_medicine_with_no_variation_page_has_no_diff(self):
        row = pd.Series({'variation_url': 'N/A'})
        assert summarise.diff_fragments(row, PAGES) == ([], [])

    def test_a_page_that_failed_to_fetch_is_skipped(self):
        """The URL is in the dataset but never made it into `pages`."""
        row = pd.Series({'variation_url': 'https://ema.example/variation/missing'})
        assert summarise.diff_fragments(row, PAGES) == ([], [])


class TestAddSummaries:
    def test_the_columns_are_added(self, prompts):
        dataset = DATASET.copy()
        summarise.add_summaries(dataset, PAGES, retriever=FakeRetriever(CHUNKS))
        assert dataset.loc[0, 'What changed'].startswith('Keytruda is now approved')
        assert dataset.loc[0, 'Summary sources'] == 'variation, NICE'

    def test_the_prompt_gets_the_numbered_passages(self, prompts):
        summarise.add_summaries(DATASET.copy(), PAGES, retriever=FakeRetriever(CHUNKS))
        prompt = prompts[0]['prompt']
        assert '[S1] variation' in prompt and '[S2] NICE' in prompt
        assert '[ADDED]in combination with chemotherapy[/ADDED]' in prompt

    def test_the_diff_is_pinned_in_even_when_the_search_missed_it(self, prompts):
        """The retrieved chunk holds no [REMOVED] span, but the prompt must."""
        summarise.add_summaries(DATASET.copy(), PAGES, retriever=FakeRetriever(CHUNKS))
        prompt = prompts[0]['prompt']
        assert 'as monotherapy in previously treated adults' in prompt

    def test_the_summariser_system_prompt_is_used(self, prompts):
        from llm import SUMMARISER_SYSTEM

        summarise.add_summaries(DATASET.copy(), PAGES, retriever=FakeRetriever(CHUNKS))
        assert prompts[0]['system'] == SUMMARISER_SYSTEM

    def test_retrieval_is_asked_for_this_medicine_only(self, prompts):
        retriever = FakeRetriever(CHUNKS)
        summarise.add_summaries(DATASET.copy(), PAGES, retriever=retriever)
        assert retriever.asked_for == ['keytruda']

    def test_retrieved_passages_can_be_logged_for_scoring(self, prompts):
        log = {}
        summarise.add_summaries(DATASET.copy(), PAGES,
                                retriever=FakeRetriever(CHUNKS), retrieval_log=log)
        assert log == {'keytruda': CHUNKS}

    def test_a_medicine_with_nothing_indexed_gets_no_summary(self, prompts):
        """Every page for it was empty or failed. Inventing a summary anyway
        would hide that, so the columns say so and the model is not called."""
        dataset = DATASET.copy()
        summarise.add_summaries(dataset, PAGES, retriever=FakeRetriever([]))
        assert dataset.loc[0, 'What changed'] == 'N/A'
        assert dataset.loc[0, 'Summary sources'] == 'no passages retrieved'
        assert prompts == []
