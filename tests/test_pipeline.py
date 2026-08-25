"""The whole pipeline over saved pages, with the model replaced by a stub.

Proves the scrapers still produce a full dataset, and that no prompt the
pipeline builds comes near the model's context window.
"""

import pandas as pd
import pytest

TOKEN_BUDGET = 30_000
CHARS_PER_TOKEN = 3.6

EXPECTED_MEDICINES = 16


@pytest.fixture
def stub_model(monkeypatch):
    """Record every prompt instead of calling the API."""
    import extractors
    import llm

    prompts = []

    def fake(prompt, system=None, attempts=3, temperature=0):
        prompts.append(prompt)
        return 'stubbed answer'

    monkeypatch.setattr(llm, 'ask_model', fake)
    monkeypatch.setattr(extractors, 'ask_model', fake)
    return prompts


@pytest.fixture
def lookup_tables():
    root = pytest.importorskip('pathlib').Path(__file__).resolve().parents[1]
    medicines = pd.read_excel(root / 'data' / 'medicines_output_medicines_en.xlsx', header=8)
    medicines['Name of medicine'] = (
        medicines['Name of medicine'].str.lower().str.replace(' ', '-')
    )
    therapy_areas = pd.read_excel(root / 'data' / 'therapy_area.xlsx')
    return medicines, therapy_areas


@pytest.fixture
def dataset(offline, stub_model, lookup_tables):
    from build_dataset import build_ema_dataset

    medicines, therapy_areas = lookup_tables
    return build_ema_dataset([], therapy_areas, medicines), stub_model


def test_pipeline_produces_one_row_per_medicine(dataset):
    """Regression: after EMA's redesign this returned zero rows."""
    frame, _ = dataset

    assert len(frame) == EXPECTED_MEDICINES
    assert frame['Product Name'].is_unique


def test_every_row_has_the_identifying_fields(dataset):
    frame, _ = dataset

    for column in ('Product Name', 'INN', 'Marketing authorisation holder', 'epar_url'):
        assert (frame[column] != 'N/A').all(), f'{column} is missing for some medicines'


def test_both_recommendation_kinds_are_represented(dataset):
    frame, _ = dataset

    assert set(frame['Initial Approval']) == {'Initial approval', 'Extension'}


def test_meeting_dates_are_filled_in(dataset):
    """Regression: the news listing lost its <time> element, blanking these."""
    frame, _ = dataset

    assert (frame['CHMP Opinion Date'] == '23 July 2026').all()
    assert (frame['date'] != 'N/A').all()


def test_no_prompt_approaches_the_context_window(dataset):
    """Regression: an untrimmed EPAR page was ~200k tokens against a 128k window."""
    _, prompts = dataset

    assert prompts, 'the pipeline made no model calls'
    largest = max(prompts, key=len)
    assert len(largest) / CHARS_PER_TOKEN < TOKEN_BUDGET, (
        f'largest prompt is ~{len(largest) / CHARS_PER_TOKEN:,.0f} tokens'
    )
