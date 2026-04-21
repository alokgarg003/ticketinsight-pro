"""
Pytest fixtures for TicketInsight Pro test suite.
"""
import pytest
import os
import sys
import tempfile

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def sample_tickets():
    """Sample ticket data for testing."""
    return [
        {
            'ticket_id': 'INC001',
            'title': 'Cannot connect to VPN',
            'description': 'I am unable to connect to the corporate VPN from my home office. '
                           'The connection times out after about 30 seconds. I have tried '
                           'restarting my computer and reinstalling the VPN client but the '
                           'issue persists. My colleague in the same building can connect fine.',
            'priority': 'High',
            'status': 'Open',
            'category': 'Network',
            'assignment_group': 'Network Support',
            'assignee': 'John Smith',
            'opened_at': '2024-01-15T09:30:00',
            'source_system': 'servicenow'
        },
        {
            'ticket_id': 'INC002',
            'title': 'Laptop screen is broken',
            'description': 'The screen on my Dell Latitude 5520 is showing vertical lines and '
                           'flickering. It happened after I closed the laptop lid and reopened it. '
                           'External monitor works fine through HDMI.',
            'priority': 'Medium',
            'status': 'In Progress',
            'category': 'Hardware',
            'assignment_group': 'Hardware Support',
            'assignee': 'Jane Doe',
            'opened_at': '2024-01-14T14:15:00',
            'source_system': 'servicenow'
        },
        {
            'ticket_id': 'INC003',
            'title': 'Password reset required',
            'description': 'I forgot my password and the self-service password reset tool is '
                           'not working. It says my account is locked after too many attempts.',
            'priority': 'Medium',
            'status': 'Resolved',
            'category': 'Access/Permissions',
            'assignment_group': 'IT Service Desk',
            'assignee': 'Bob Wilson',
            'opened_at': '2024-01-13T11:00:00',
            'resolved_at': '2024-01-13T11:45:00',
            'source_system': 'jira'
        },
        {
            'ticket_id': 'INC004',
            'title': 'Outlook keeps crashing',
            'description': 'Microsoft Outlook 365 keeps crashing every time I try to open an '
                           'email with an attachment larger than 5MB. I have already tried '
                           'repairing the Office installation and clearing the Outlook cache. '
                           'The error code is 0x80070005.',
            'priority': 'High',
            'status': 'Open',
            'category': 'Software',
            'assignment_group': 'Application Support',
            'assignee': 'Alice Brown',
            'opened_at': '2024-01-12T16:30:00',
            'source_system': 'servicenow'
        },
        {
            'ticket_id': 'INC005',
            'title': 'Need access to Salesforce',
            'description': 'I am a new hire starting in the Marketing department and need access '
                           'to Salesforce CRM. My manager has approved this request.',
            'priority': 'Low',
            'status': 'Closed',
            'category': 'Access/Permissions',
            'assignment_group': 'Access Management',
            'assignee': 'Carol Davis',
            'opened_at': '2024-01-10T08:00:00',
            'resolved_at': '2024-01-10T16:00:00',
            'closed_at': '2024-01-10T16:30:00',
            'source_system': 'servicenow'
        }
    ]


@pytest.fixture
def sample_config():
    """Sample configuration dict for testing."""
    return {
        'app': {'env': 'test', 'debug': True, 'port': 5000, 'host': '0.0.0.0'},
        'database': {'url': 'sqlite:///:memory:', 'pool_size': 5},
        'redis': {'url': 'redis://localhost:6379/0', 'cache_ttl': 300},
        'logging': {'level': 'DEBUG', 'file': None},
        'adapter': {'type': 'csv'},
        'nlp': {'model': 'en_core_web_sm', 'batch_size': 50},
        'pipeline': {'interval_minutes': 60}
    }


@pytest.fixture
def tmp_csv_file():
    """Create a temporary CSV file for testing."""
    import csv
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(['ticket_id', 'title', 'description', 'priority', 'status'])
        writer.writerow(['T001', 'VPN Issue', 'Cannot connect to VPN from home', 'High', 'Open'])
        writer.writerow(['T002', 'Screen Broken', 'Laptop screen shows vertical lines', 'Medium', 'In Progress'])
        writer.writerow(['T003', 'Password Reset', 'Forgot password and account locked', 'Medium', 'Resolved'])
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)
