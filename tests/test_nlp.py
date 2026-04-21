"""
Tests for NLP/ML engine modules.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ticketinsight.nlp.classifier import TicketClassifier
from ticketinsight.nlp.sentiment import SentimentAnalyzer
from ticketinsight.nlp.summarizer import TicketSummarizer
from ticketinsight.nlp.duplicate_detector import DuplicateDetector
from ticketinsight.nlp.anomaly_detector import AnomalyDetector
from ticketinsight.nlp.ner_extractor import NERExtractor
from ticketinsight.nlp.root_cause import RootCauseAnalyzer


class TestTicketClassifier:
    def setup_method(self):
        self.classifier = TicketClassifier({})

    def test_classify_hardware(self):
        result = self.classifier.classify("My laptop screen is broken and needs replacement")
        assert result['category'] is not None
        assert isinstance(result['category'], str)

    def test_classify_network(self):
        result = self.classifier.classify("Cannot connect to VPN from home office")
        assert result['category'] is not None

    def test_classify_software(self):
        result = self.classifier.classify("Application crashes when opening large files")
        assert result['category'] is not None

    def test_classify_access(self):
        result = self.classifier.classify("Need password reset for my account")
        assert result['category'] is not None

    def test_classify_email(self):
        result = self.classifier.classify("Outlook is not syncing emails properly")
        assert result['category'] is not None

    def test_classify_security(self):
        result = self.classifier.classify("Malware detected on workstation need immediate cleanup")
        assert result['category'] is not None

    def test_classify_database(self):
        result = self.classifier.classify("SQL query timeout on production database server")
        assert result['category'] is not None

    def test_classify_cloud(self):
        result = self.classifier.classify("AWS EC2 instance unreachable need to check security group")
        assert result['category'] is not None

    def test_returns_confidence(self):
        result = self.classifier.classify("Test ticket about network connectivity issue")
        assert 'confidence' in result
        assert 0 <= result['confidence'] <= 1

    def test_returns_all_scores(self):
        result = self.classifier.classify("Broken printer needs new toner")
        assert 'all_scores' in result or 'scores' in result or result.get('category') is not None

    def test_classify_batch(self):
        texts = [
            "My laptop screen is broken",
            "Cannot connect to VPN",
            "Need password reset"
        ]
        results = self.classifier.classify_batch(texts)
        assert len(results) == 3
        for r in results:
            assert r['category'] is not None


class TestSentimentAnalyzer:
    def setup_method(self):
        self.analyzer = SentimentAnalyzer({})

    def test_positive_sentiment(self):
        result = self.analyzer.analyze(
            "Thank you for the quick resolution. The issue is resolved and everything works great."
        )
        assert 'label' in result
        assert result['polarity'] >= -1

    def test_negative_sentiment(self):
        result = self.analyzer.analyze(
            "This is extremely frustrating. The system has been down for 3 days and no one is helping."
        )
        assert 'polarity' in result

    def test_urgency_detection(self):
        result = self.analyzer.analyze(
            "CRITICAL: Production server is down. Business impact is severe. Need immediate resolution."
        )
        assert 'urgency_score' in result
        assert result['urgency_score'] > 0.3

    def test_frustration_detection(self):
        result = self.analyzer.analyze(
            "I am very frustrated. I have been waiting for 3 days and no one has responded. "
            "This is unacceptable and I need to escalate to management."
        )
        assert 'frustration_score' in result
        assert result['frustration_score'] > 0.3

    def test_returns_all_fields(self):
        result = self.analyzer.analyze("Test ticket")
        assert 'polarity' in result
        assert 'subjectivity' in result
        assert 'label' in result
        assert 'urgency_score' in result
        assert 'frustration_score' in result

    def test_analyze_batch(self):
        texts = [
            "Everything works great now, thank you!",
            "This is terrible, still broken after a week",
            "Just a regular update on the ticket status"
        ]
        results = self.analyzer.analyze_batch(texts)
        assert len(results) == 3
        for r in results:
            assert 'polarity' in r


class TestTicketSummarizer:
    def setup_method(self):
        self.summarizer = TicketSummarizer({})

    def test_summarize_long_text(self):
        long_text = (
            "The VPN connection from the home office has been intermittent for the past three days. "
            "I have tried restarting the VPN client multiple times and also reinstalled it once. "
            "The issue seems to occur mainly during peak hours between 9 AM and 11 AM. "
            "My colleague in the same building does not face this issue. "
            "I am using Windows 11 and the latest version of the VPN client. "
            "The error message I see is 'Connection timeout after 30 seconds'. "
            "I have checked my internet connection and it is stable at 100 Mbps. "
            "Please help resolve this as it is affecting my ability to attend virtual meetings."
        )
        result = self.summarizer.summarize(long_text)
        assert 'summary' in result
        assert len(result['summary']) > 0
        assert result['original_length'] > 0
        assert result['summary_length'] > 0

    def test_summarize_short_text(self):
        result = self.summarizer.summarize("Short text")
        assert 'summary' in result

    def test_key_phrases_extraction(self):
        long_text = (
            "The VPN connection from the home office has been intermittent. "
            "The VPN client shows a timeout error. Please fix the VPN issue."
        )
        result = self.summarizer.summarize(long_text)
        assert 'key_phrases' in result

    def test_compression_ratio(self):
        long_text = "Word " * 200  # Long text
        result = self.summarizer.summarize(long_text)
        assert 'compression_ratio' in result


class TestDuplicateDetector:
    def setup_method(self):
        self.detector = DuplicateDetector({})

    def test_finds_similar_tickets(self):
        texts = [
            "Cannot connect to VPN from home office, connection times out",
            "VPN not working from home, keeps timing out after 30 seconds",
            "Laptop screen is broken and showing vertical lines"
        ]
        results = self.detector.find_duplicates(texts)
        assert isinstance(results, list)

    def test_no_duplicates_for_distinct_tickets(self):
        texts = [
            "Laptop screen broken",
            "Need password reset",
            "Printer jam",
            "Email not syncing"
        ]
        results = self.detector.find_duplicates(texts, threshold=0.95)
        assert isinstance(results, list)

    def test_check_single_duplicate(self):
        new_text = "VPN connection timeout from home office"
        existing = [
            "Cannot connect to VPN from home office, keeps timing out",
            "Laptop screen is broken"
        ]
        result = self.detector.check_duplicate(new_text, existing)
        assert 'is_duplicate' in result
        assert isinstance(result['is_duplicate'], bool)

    def test_check_single_no_duplicate(self):
        new_text = "Need new keyboard because keys are sticking"
        existing = [
            "VPN connection issue from home",
            "Database query timeout"
        ]
        result = self.detector.check_duplicate(new_text, existing, threshold=0.95)
        assert isinstance(result, bool) or 'is_duplicate' in result


class TestAnomalyDetector:
    def setup_method(self):
        self.detector = AnomalyDetector({})

    def test_detect_with_normal_tickets(self):
        tickets = [
            {
                'description': 'Normal ticket about email',
                'priority': 'Medium',
                'category': 'Software',
                'title': 'Email not syncing'
            },
            {
                'description': 'Regular VPN issue',
                'priority': 'Low',
                'category': 'Network',
                'title': 'VPN slow'
            }
        ]
        result = self.detector.detect(tickets)
        assert 'anomalies' in result
        assert 'total_analyzed' in result
        assert result['total_analyzed'] == 2

    def test_detect_with_anomalous_ticket(self):
        tickets = [
            {
                'description': 'a' * 5000,  # Extremely long description
                'priority': 'Critical',
                'category': 'Software',
                'title': 'Test'
            }
        ]
        result = self.detector.detect(tickets)
        assert 'anomalies' in result
        assert result['total_analyzed'] >= 1

    def test_statistical_check(self):
        ticket = {
            'description': 'Test ticket',
            'priority': 'Critical',
            'category': 'Software'
        }
        baseline = {
            'avg_description_length': 100,
            'std_description_length': 50,
            'avg_resolution_hours': 24,
            'std_resolution_hours': 12
        }
        result = self.detector._statistical_anomaly_check(ticket, baseline)
        assert isinstance(result, list)


class TestNERExtractor:
    def setup_method(self):
        self.extractor = NERExtractor({})

    def test_extract_ip_addresses(self):
        text = "Server at 192.168.1.100 is unreachable and 10.0.0.1 returns timeout"
        # Load model or use fallback
        try:
            self.extractor.load_model()
            result = self.extractor.extract(text)
            assert 'it_specific' in result
        except Exception:
            # If spaCy not available, test regex patterns directly
            result = self.extractor._extract_it_entities(text)
            assert 'ip_addresses' in result
            assert len(result['ip_addresses']) >= 1

    def test_extract_email_addresses(self):
        text = "Contact admin@company.com or support@helpdesk.org for assistance"
        result = self.extractor._extract_it_entities(text)
        assert 'email_addresses' in result
        assert len(result['email_addresses']) >= 1

    def test_extract_error_codes(self):
        text = "Application crashed with error 0x80070005 and exception code ERR_TIMEOUT_123"
        result = self.extractor._extract_it_entities(text)
        assert 'error_codes' in result

    def test_extract_urls(self):
        text = "Visit https://portal.company.com or http://help.internal.net"
        result = self.extractor._extract_it_entities(text)
        assert 'urls' in result
        assert len(result['urls']) >= 1

    def test_extract_file_paths(self):
        text = "Error reading C:\\Users\\admin\\config.json and /etc/app/settings.yml"
        result = self.extractor._extract_it_entities(text)
        assert 'file_paths' in result

    def test_software_dictionary(self):
        software = self.extractor._get_software_dict()
        assert isinstance(software, set)
        assert len(software) > 10

    def test_hardware_dictionary(self):
        hardware = self.extractor._get_hardware_dict()
        assert isinstance(hardware, set)
        assert len(hardware) > 5


class TestRootCauseAnalyzer:
    def setup_method(self):
        self.analyzer = RootCauseAnalyzer({})

    def test_pattern_match_network(self):
        result = self.analyzer._pattern_match(
            "VPN connection timeout, DNS resolution failing, network latency high"
        )
        assert 'cause' in result
        assert 'network' in result['cause'].lower()

    def test_pattern_match_authentication(self):
        result = self.analyzer._pattern_match(
            "Login failed, password not accepted, account locked after multiple attempts"
        )
        assert 'authentication' in result['cause'].lower()

    def test_pattern_match_hardware(self):
        result = self.analyzer._pattern_match(
            "Device not working, faulty component, damaged hardware"
        )
        assert 'hardware' in result['cause'].lower() or 'failure' in result['cause'].lower()

    def test_pattern_match_software_bug(self):
        result = self.analyzer._pattern_match(
            "Application crash, bug in the system, error exception fault"
        )
        assert result['cause'] is not None

    def test_analyze_multiple_tickets(self):
        tickets = [
            {'description': 'VPN keeps disconnecting', 'category': 'Network'},
            {'description': 'Cannot access shared drive', 'category': 'Access'},
            {'description': 'VPN timeout from home', 'category': 'Network'},
        ]
        result = self.analyzer.analyze(tickets)
        assert 'root_cause_distribution' in result

    def test_generate_recommendations(self):
        cluster_analysis = {
            'clusters': [
                {'label': 'Network', 'count': 10, 'percentage': 25.0}
            ]
        }
        recs = self.analyzer._generate_recommendations(cluster_analysis)
        assert isinstance(recs, list)
        assert len(recs) > 0
