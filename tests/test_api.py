"""
Tests for Flask API endpoints.
"""
import pytest
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'status' in data


class TestTicketEndpoints:
    def test_get_tickets(self, client):
        response = client.get('/api/v1/tickets')
        assert response.status_code == 200
        data = json.loads(response.data)

    def test_get_tickets_with_pagination(self, client):
        response = client.get('/api/v1/tickets?page=1&per_page=5')
        assert response.status_code == 200

    def test_get_tickets_with_filters(self, client):
        response = client.get('/api/v1/tickets?status=Open&priority=High')
        assert response.status_code == 200

    def test_get_tickets_with_search(self, client):
        response = client.get('/api/v1/tickets?search=VPN')
        assert response.status_code == 200

    def test_get_ticket_not_found(self, client):
        response = client.get('/api/v1/tickets/99999')
        assert response.status_code == 404

    def test_get_tickets_sort_ascending(self, client):
        response = client.get('/api/v1/tickets?sort_by=ticket_id&sort_order=asc')
        assert response.status_code == 200


class TestInsightEndpoints:
    def test_insights_summary(self, client):
        response = client.get('/api/v1/insights/summary')
        assert response.status_code == 200

    def test_sentiment_insights(self, client):
        response = client.get('/api/v1/insights/sentiment')
        assert response.status_code == 200

    def test_topic_insights(self, client):
        response = client.get('/api/v1/insights/topics')
        assert response.status_code == 200

    def test_duplicate_insights(self, client):
        response = client.get('/api/v1/insights/duplicates')
        assert response.status_code == 200

    def test_anomaly_insights(self, client):
        response = client.get('/api/v1/insights/anomalies')
        assert response.status_code == 200

    def test_root_cause_insights(self, client):
        response = client.get('/api/v1/insights/root-causes')
        assert response.status_code == 200

    def test_performance_insights(self, client):
        response = client.get('/api/v1/insights/performance')
        assert response.status_code == 200


class TestDashboardEndpoints:
    def test_dashboard_stats(self, client):
        response = client.get('/api/v1/dashboard/statistics')
        assert response.status_code == 200

    def test_dashboard_trends(self, client):
        response = client.get('/api/v1/dashboard/trends')
        assert response.status_code == 200

    def test_dashboard_trends_with_params(self, client):
        response = client.get('/api/v1/dashboard/trends?period=weekly&days=30')
        assert response.status_code == 200


class TestAdapterEndpoints:
    def test_adapter_status(self, client):
        response = client.get('/api/v1/adapter/status')
        assert response.status_code == 200


class TestPipelineEndpoints:
    def test_pipeline_status(self, client):
        response = client.get('/api/v1/pipeline/status')
        assert response.status_code == 200

    def test_config_get(self, client):
        response = client.get('/api/v1/config')
        assert response.status_code == 200


class TestErrorHandling:
    def test_404_for_unknown_route(self, client):
        response = client.get('/api/v1/nonexistent')
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        response = client.delete('/api/v1/tickets')
        assert response.status_code == 405

    def test_invalid_json_input(self, client):
        response = client.post(
            '/api/v1/ingest',
            data='not json',
            content_type='application/json'
        )
        assert response.status_code == 400
