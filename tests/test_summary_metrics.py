"""Metrics for the summary column, and the label-free checks over it.

The point of these is less the arithmetic than the property the three numbers
exist for together: ROUGE cannot tell a flipped negation from the truth, and the
other two can.
"""

import pandas as pd

import grounding
import metrics

REFERENCE = ('Keytruda is now approved in combination with chemotherapy for the '
             'first-line treatment of adults with advanced gastric cancer.')

CONTEXT = ('[S1] variation\nKeytruda is indicated [ADDED]in combination with '
           'chemotherapy for the first-line treatment of adults with advanced '
           'gastric cancer[/ADDED].')


class TestRouge:
    def test_identical_summaries_score_one(self):
        scores = metrics.rouge_scores(REFERENCE, REFERENCE)
        assert scores['rouge1_f'] == 1.0 and scores['rougeL_f'] == 1.0

    def test_citations_do_not_count_against_the_score(self):
        assert metrics.rouge_scores(f'{REFERENCE} [S1]', REFERENCE)['rougeL_f'] == 1.0

    def test_unrelated_summaries_score_low(self):
        assert metrics.rouge_scores('Nothing was changed.', REFERENCE)['rougeL_f'] < 0.3

    def test_a_flipped_negation_still_scores_high(self):
        """Which is exactly why ROUGE is never reported on its own."""
        wrong = REFERENCE.replace('is now approved', 'is not approved')
        assert metrics.rouge_scores(wrong, REFERENCE)['rougeL_f'] > 0.85

    def test_an_empty_prediction_scores_zero(self):
        assert metrics.rouge_scores('', REFERENCE)['rouge1_f'] == 0.0


class TestSupportedFraction:
    def test_a_summary_taken_from_its_sources_is_fully_supported(self):
        summary = ('Keytruda is indicated in combination with chemotherapy for the '
                   'first-line treatment of adults with advanced gastric cancer. [S1]')
        assert metrics.supported_fraction(summary, CONTEXT) == 1.0

    def test_invented_content_lowers_the_score(self):
        summary = ('Keytruda doubled overall survival versus docetaxel in a '
                   'randomised phase three trial. [S1]')
        assert metrics.supported_fraction(summary, CONTEXT) < 0.5

    def test_stopwords_cannot_prop_the_score_up(self):
        assert metrics.supported_fraction('It is at the of and to.', CONTEXT) == 1.0

    def test_no_context_means_nothing_is_supported(self):
        assert metrics.supported_fraction('Keytruda gastric cancer', '') == 0.0


class TestCitationRate:
    def test_every_sentence_cited(self):
        assert metrics.citation_rate('First sentence. [S1] Second sentence. [S2]', 3) == 1.0

    def test_a_citation_before_the_full_stop_counts_too(self):
        assert metrics.citation_rate('First sentence [S1]. Second sentence [S2].', 3) == 1.0

    def test_uncited_sentences_are_counted(self):
        assert metrics.citation_rate('First. [S1] Second, with no citation.', 3) == 0.5

    def test_a_citation_beyond_the_retrieved_passages_does_not_count(self):
        """[S9] against four passages is an invented reference."""
        assert metrics.citation_rate('One sentence. [S9]', 4) == 0.0

    def test_empty_summary(self):
        assert metrics.citation_rate('', 4) == 0.0


class TestSummaryReport:
    def test_averages_over_a_run(self):
        report = metrics.summary_report([REFERENCE, REFERENCE],
                                        references=[REFERENCE, 'Something else entirely.'])
        assert report['n'] == 2 and 0 < report['rougeL_f'] < 1

    def test_summaries_the_model_declined_to_write_are_not_scored(self):
        report = metrics.summary_report(['Not stated', REFERENCE],
                                        references=[REFERENCE, REFERENCE])
        assert report['n'] == 1

    def test_works_with_no_references_at_all(self):
        report = metrics.summary_report([REFERENCE], contexts=[CONTEXT], chunk_counts=[1])
        assert report['n'] == 1
        assert 'supported_fraction' in report and 'rougeL_f' not in report

    def test_nothing_to_score(self):
        assert metrics.summary_report([])['n'] == 0


VARIATION_HTML = ('<p>Keytruda is indicated <strong>in combination with chemotherapy'
                  '</strong>, <s>as monotherapy</s>.</p>')

PAGES = {'https://ema.example/variation/keytruda': VARIATION_HTML}

DATASET = pd.DataFrame([{
    'Product Name': 'keytruda',
    'variation_url': 'https://ema.example/variation/keytruda',
    'What changed': 'Keytruda is now given in combination with chemotherapy. [S1]',
}])


class TestRetrievalCheck:
    def test_full_recall_when_both_spans_were_retrieved(self):
        chunks = [{'text': '[ADDED]in combination with chemotherapy[/ADDED] '
                           '[REMOVED]as monotherapy[/REMOVED]', 'metadata': {}}]
        findings = grounding.check_retrieval(DATASET, {'keytruda': chunks}, PAGES)
        assert findings[0]['recall'] == 1.0
        assert grounding.mean_recall(findings) == 1.0

    def test_a_missed_span_is_named(self):
        chunks = [{'text': '[ADDED]in combination with chemotherapy[/ADDED]',
                   'metadata': {}}]
        findings = grounding.check_retrieval(DATASET, {'keytruda': chunks}, PAGES)
        assert findings[0]['recall'] == 0.5
        assert findings[0]['missed'] == ['as monotherapy']

    def test_a_medicine_with_nothing_marked_up_is_not_scored(self):
        """A first authorisation has no diff, so there is no recall to measure."""
        dataset = pd.DataFrame([{'Product Name': 'jivi', 'variation_url': 'N/A'}])
        findings = grounding.check_retrieval(dataset, {'jivi': []}, PAGES)
        assert findings == []
        assert grounding.mean_recall(findings) is None


class TestSummaryCheck:
    def test_a_grounded_summary_passes(self):
        chunks = [{'text': 'Keytruda is now given in combination with chemotherapy.',
                   'metadata': {'source': 'variation', 'url': ''}}]
        finding = grounding.check_summaries(DATASET, {'keytruda': chunks})[0]
        assert finding['verdict'] == 'grounded'
        assert finding['citation_rate'] == 1.0

    def test_an_invented_summary_is_flagged(self):
        chunks = [{'text': 'Keytruda is indicated for melanoma.',
                   'metadata': {'source': 'EPAR indication', 'url': ''}}]
        finding = grounding.check_summaries(DATASET, {'keytruda': chunks})[0]
        assert finding['verdict'] == 'ungrounded'

    def test_a_medicine_with_no_summary_is_skipped(self):
        dataset = DATASET.copy()
        dataset.loc[0, 'What changed'] = 'N/A'
        assert grounding.check_summaries(dataset, {}) == []
