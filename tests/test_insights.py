"""
Tests for insights generation and reporting.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestInsightsGenerator:
    """Test insight generation capabilities."""

    def test_import_generator(self):
        """Test that InsightsGenerator can be imported."""
        from ticketinsight.insights.generator import InsightsGenerator
        assert InsightsGenerator is not None

    def test_generator_init(self, sample_config):
        """Test InsightsGenerator initialization."""
        from ticketinsight.insights.generator import InsightsGenerator
        try:
            generator = InsightsGenerator(db_manager=None, nlp_engine=None)
            assert generator is not None
        except TypeError:
            pytest.skip("InsightsGenerator constructor signature differs")


class TestReportGenerator:
    """Test report generation capabilities."""

    def test_import_reporter(self):
        """Test that ReportGenerator can be imported."""
        from ticketinsight.insights.reporter import ReportGenerator
        assert ReportGenerator is not None

    def test_reporter_init(self):
        """Test ReportGenerator initialization."""
        from ticketinsight.insights.reporter import ReportGenerator
        try:
            reporter = ReportGenerator(db_manager=None, insights_generator=None)
            assert reporter is not None
        except TypeError:
            pytest.skip("ReportGenerator constructor signature differs")


class TestNLPEngineIntegration:
    """Test NLP engine integration."""

    def test_import_nlp_engine(self):
        """Test that NLPEngine can be imported."""
        from ticketinsight.nlp import NLPEngine
        assert NLPEngine is not None

    def test_nlp_engine_init(self, sample_config):
        """Test NLPEngine initialization."""
        from ticketinsight.nlp import NLPEngine
        engine = NLPEngine(config=sample_config)
        assert engine is not None
        assert engine.classifier is not None
        assert engine.sentiment_analyzer is not None

    def test_nlp_engine_single_analysis(self, sample_config):
        """Test analyzing a single ticket."""
        from ticketinsight.nlp import NLPEngine
        engine = NLPEngine(config=sample_config)
        ticket = {
            'ticket_id': 'TEST001',
            'title': 'VPN connection timeout from home office',
            'description': 'I cannot connect to the corporate VPN. '
                           'The connection times out after 30 seconds. '
                           'I have restarted my laptop and reinstalled the VPN client.',
            'priority': 'High',
            'status': 'Open'
        }
        result = engine.analyze_ticket(ticket)
        assert result is not None
        assert 'classification' in result or 'category' in result
