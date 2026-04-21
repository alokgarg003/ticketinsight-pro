"""
Tests for data adapters.
"""
import pytest
import sys
import os
import csv
import tempfile
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from ticketinsight.adapters.base import BaseAdapter
from ticketinsight.adapters.csv_importer import CSVImporterAdapter


class TestBaseAdapter:
    def setup_method(self):
        self.adapter = BaseAdapter({'test': True})

    def test_normalize_ticket_standard_fields(self):
        raw = {
            'ticket_id': 'INC001',
            'title': 'Test Ticket',
            'description': 'Test description',
            'priority': 'High',
            'status': 'Open'
        }
        result = self.adapter.normalize_ticket(raw)
        assert result['ticket_id'] == 'INC001'
        assert result['title'] == 'Test Ticket'
        assert result['description'] == 'Test description'

    def test_normalize_ticket_alias_number(self):
        raw = {'number': 'INC002', 'short_description': 'Another Ticket'}
        result = self.adapter.normalize_ticket(raw)
        assert result['ticket_id'] == 'INC002'
        assert result['title'] == 'Another Ticket'

    def test_normalize_ticket_alias_sys_id(self):
        raw = {'sys_id': 'SYS123', 'short_description': 'System Ticket'}
        result = self.adapter.normalize_ticket(raw)
        assert result['ticket_id'] == 'SYS123'

    def test_normalize_ticket_alias_state(self):
        raw = {'number': 'T001', 'state': '2', 'title': 'Test'}
        result = self.adapter.normalize_ticket(raw)
        assert result['status'] == 'In Progress'

    def test_normalize_ticket_alias_urgency_impact(self):
        raw = {
            'number': 'T002',
            'title': 'Test',
            'urgency': '1',
            'impact': '1'
        }
        result = self.adapter.normalize_ticket(raw)
        assert result['priority'] == 'Critical'

    def test_normalize_ticket_empty_input(self):
        result = self.adapter.normalize_ticket({})
        assert 'ticket_id' in result

    def test_normalize_ticket_preserves_source(self):
        raw = {'ticket_id': 'T001', 'title': 'Test', 'source_system': 'jira'}
        result = self.adapter.normalize_ticket(raw)
        assert result['source_system'] == 'jira'

    def test_abstract_methods_raise(self):
        with pytest.raises(TypeError):
            adapter = BaseAdapter({})
            adapter.connect()

    def test_close_no_error(self):
        self.adapter.close()  # Should not raise


class TestCSVAdapter:
    def test_read_csv_file(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        adapter.connect()
        tickets = adapter.fetch_tickets()
        assert len(tickets) == 3
        assert tickets[0]['ticket_id'] == 'T001'
        assert tickets[0]['title'] == 'VPN Issue'

    def test_read_with_limit(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        adapter.connect()
        tickets = adapter.fetch_tickets(limit=2)
        assert len(tickets) == 2

    def test_read_with_offset(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        adapter.connect()
        tickets = adapter.fetch_tickets(offset=1)
        assert len(tickets) == 2
        assert tickets[0]['ticket_id'] == 'T002'

    def test_health_check(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        result = adapter.health_check()
        assert result['status'] == 'healthy'
        assert 'total_rows' in result

    def test_fetch_single_ticket(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        adapter.connect()
        ticket = adapter.fetch_ticket('T001')
        assert ticket is not None
        assert ticket['ticket_id'] == 'T001'

    def test_column_mapping(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'subject', 'body', 'severity', 'state'])
            writer.writerow(['C001', 'Custom Title', 'Custom description', 'High', 'Open'])
            temp_path = f.name

        try:
            config = {
                'file_path': temp_path,
                'column_map': {
                    'id': 'ticket_id',
                    'subject': 'title',
                    'body': 'description',
                    'severity': 'priority',
                    'state': 'status'
                }
            }
            adapter = CSVImporterAdapter(config)
            adapter.connect()
            tickets = adapter.fetch_tickets()
            assert len(tickets) == 1
            assert tickets[0]['ticket_id'] == 'C001'
            assert tickets[0]['title'] == 'Custom Title'
            assert tickets[0]['description'] == 'Custom description'
        finally:
            os.unlink(temp_path)

    def test_empty_csv_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['ticket_id', 'title'])
            temp_path = f.name

        try:
            adapter = CSVImporterAdapter({'file_path': temp_path})
            adapter.connect()
            tickets = adapter.fetch_tickets()
            assert len(tickets) == 0
        finally:
            os.unlink(temp_path)

    def test_missing_file(self):
        adapter = CSVImporterAdapter({'file_path': '/nonexistent/file.csv'})
        result = adapter.health_check()
        assert result['status'] == 'unhealthy'

    def test_close_connection(self, tmp_csv_file):
        adapter = CSVImporterAdapter({'file_path': tmp_csv_file})
        adapter.connect()
        adapter.close()  # Should not raise


class TestServiceNowAdapter:
    @patch('requests.Session')
    def test_health_check_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': [{'name': 'incident'}]}
        mock_session.get.return_value = mock_response

        from ticketinsight.adapters.servicenow import ServiceNowAdapter
        adapter = ServiceNowAdapter({
            'instance_url': 'https://test.service-now.com',
            'username': 'admin',
            'password': 'pass'
        })
        result = adapter.health_check()
        assert result['status'] == 'healthy'

    @patch('requests.Session')
    def test_health_check_auth_failure(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.get.return_value = mock_response

        from ticketinsight.adapters.servicenow import ServiceNowAdapter
        adapter = ServiceNowAdapter({
            'instance_url': 'https://test.service-now.com',
            'username': 'admin',
            'password': 'wrong'
        })
        result = adapter.health_check()
        assert result['status'] == 'unhealthy'


class TestJiraAdapter:
    @patch('requests.Session')
    def test_health_check_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'displayName': 'Test User'}
        mock_session.get.return_value = mock_response

        from ticketinsight.adapters.jira import JiraAdapter
        adapter = JiraAdapter({
            'server': 'https://test.atlassian.net',
            'email': 'test@example.com',
            'api_token': 'token123'
        })
        result = adapter.health_check()
        assert result['status'] == 'healthy'
