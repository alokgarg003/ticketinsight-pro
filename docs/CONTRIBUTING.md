# Contributing to TicketInsight Pro

Thank you for your interest in contributing to TicketInsight Pro! This guide
covers everything you need to know to contribute effectively.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Making Changes](#making-changes)
- [Writing Code](#writing-code)
- [Testing](#testing)
- [Documentation](#documentation)
- [Commit Messages](#commit-messages)
- [Pull Requests](#pull-requests)
- [Issue Reporting](#issue-reporting)
- [Contributor Areas](#contributor-areas)
- [Release Process](#release-process)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming, inclusive, and harassment-free
experience for everyone. Please be respectful and constructive in all interactions.

### Standards

- **Be respectful**: Treat all contributors with dignity and respect
- **Be constructive**: Provide helpful feedback focused on the code, not the person
- **Be inclusive**: Use inclusive language and welcome newcomers
- **Be collaborative**: Work together to find the best solutions
- **Be patient**: Remember that everyone was new to this project once

### Unacceptable Behavior

- Harassment, discrimination, or derogatory language
- Personal attacks or insulting comments
- Publishing others' private information
- Trolling, flaming, or baiting

---

## Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.9+ | Language runtime |
| Git | 2.30+ | Version control |
| pip | 21.0+ | Package manager |
| Docker | 20.10+ | Container runtime (optional) |
| Node.js | 18+ | Frontend build (optional) |
| Make | 4.0+ | Task runner (optional) |

### Fork and Clone

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/ticketinsight-pro.git
cd ticketinsight-pro

# 3. Add upstream remote
git remote add upstream https://github.com/yourorg/ticketinsight-pro.git

# 4. Verify remotes
git remote -v
# origin    https://github.com/YOUR_USERNAME/ticketinsight-pro.git (fetch)
# upstream  https://github.com/yourorg/ticketinsight-pro.git (fetch)
```

### Keep Your Fork Updated

```bash
# Fetch upstream changes
git fetch upstream

# Rebase your main branch
git checkout main
git rebase upstream/main

# Push to your fork
git push origin main --force-with-lease
```

---

## Development Environment

### Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with development dependencies
pip install -e ".[dev]"

# Copy and configure
cp config.example.yaml config.yaml

# Initialize the database
ticketinsight db init

# Seed sample data (optional)
ticketinsight db seed --sample-size 1000

# Verify everything works
pytest
ticketinsight config validate
```

### Project Structure Overview

```
src/ticketinsight/
├── api/           # REST API route handlers
├── adapters/      # Data source adapters (BaseAdapter protocol)
├── nlp/           # NLP pipeline components
├── ml/            # Machine learning models
├── analytics/     # Analytics and KPI engine
├── processing/    # Pipeline orchestration
├── models/        # Database ORM models
├── utils/         # Shared utilities
└── cli/           # CLI command definitions

tests/
├── test_api/      # API endpoint tests
├── test_nlp/      # NLP component tests
├── test_ml/       # ML model tests
├── test_adapters/ # Adapter tests
└── test_analytics/ # Analytics engine tests
```

### Development Tools

```bash
# Run the development server with auto-reload
ticketinsight serve --reload --debug

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/ticketinsight --cov-report=html --cov-report=term-missing

# Lint code
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Type check
mypy src/ticketinsight

# Security scan
bandit -r src/ticketinsight

# Run all checks at once
make lint
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# This will automatically run on every commit:
# - ruff format (auto-format)
# - ruff check (lint)
# - mypy (type check)
# - trailing whitespace fix
# - YAML/JSON validation
```

---

## Making Changes

### Branch Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/short-description` | `feature/zendesk-adapter` |
| Bug fix | `fix/short-description` | `fix/csv-encoding-crash` |
| Documentation | `docs/short-description` | `docs/api-examples` |
| Refactor | `refactor/short-description` | `refactor/nlp-pipeline` |
| Test | `test/short-description` | `test/anomaly-detector` |
| Chore | `chore/short-description` | `chore/update-deps` |

### Creating a Feature Branch

```bash
# Start from an updated main
git checkout main
git pull upstream main

# Create and switch to feature branch
git checkout -b feature/my-new-feature

# Make your changes, commit frequently
git add ...
git commit -m "feat: add description of change"

# Push to your fork
git push -u origin feature/my-new-feature
```

### What to Include

- **Code changes**: The actual implementation
- **Tests**: Unit tests for new/changed behavior
- **Documentation**: Updated docstrings, README, and/or docs
- **Type hints**: All function signatures should be typed
- **Error handling**: Graceful failure with helpful messages
- **Changelog**: Add entry to `docs/CHANGELOG.md` under "Unreleased"

---

## Writing Code

### Python Style Guide

We follow [PEP 8](https://peps.python.org/pep-0008/) with some extensions
enforced by `ruff`:

```python
"""Module docstring describing the purpose of this module."""

from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ExampleModel:
    """A short description of this class.

    Longer description if needed, explaining the purpose,
    usage patterns, and important considerations.

    Attributes:
        name: The name of the example.
        value: The numeric value, defaults to 0.
    """

    name: str
    value: int = 0
    tags: list[str] = field(default_factory=list)

    def compute(self, multiplier: int = 1) -> int:
        """Compute the result by multiplying value.

        Args:
            multiplier: The multiplier to apply. Must be positive.

        Returns:
            The computed result.

        Raises:
            ValueError: If multiplier is negative.
        """
        if multiplier < 0:
            raise ValueError("Multiplier must be non-negative")
        return self.value * multiplier
```

### Key Style Rules

| Rule | Description |
|------|-------------|
| **Imports** | Grouped: stdlib, third-party, local. Use `isort` (via ruff) |
| **String quotes** | Double quotes for strings, single quotes for dict keys |
| **Line length** | 100 characters maximum |
| **Type hints** | Required for all function signatures |
| **Docstrings** | Google-style docstrings for all public classes and functions |
| **Naming** | `snake_case` for functions/variables, `PascalCase` for classes |
| **Constants** | `UPPER_SNAKE_CASE` for module-level constants |

### Error Handling Pattern

```python
from ticketinsight.utils.exceptions import (
    TicketInsightError,
    ValidationError,
    AdapterError,
)

def process_ticket(ticket_id: str) -> ProcessResult:
    """Process a single ticket.

    Wraps errors in domain-specific exceptions with context.
    """
    try:
        ticket = fetch_ticket(ticket_id)
    except ConnectionError as e:
        raise AdapterError(
            adapter="servicenow",
            message=f"Failed to fetch ticket {ticket_id}: {e}",
        ) from e

    if not ticket.description:
        raise ValidationError(
            message=f"Ticket {ticket_id} has no description",
            details={"ticket_id": ticket_id, "field": "description"},
        )

    return ProcessResult(ticket_id=ticket_id, status="success")
```

### Logging Pattern

```python
import logging

logger = logging.getLogger(__name__)

class TicketService:
    def process(self, ticket_id: str) -> None:
        logger.info("Processing ticket", extra={
            "ticket_id": ticket_id,
            "operation": "process",
        })

        try:
            result = self._do_process(ticket_id)
            logger.info("Ticket processed successfully", extra={
                "ticket_id": ticket_id,
                "result": result,
            })
        except Exception:
            logger.exception("Failed to process ticket", extra={
                "ticket_id": ticket_id,
            })
            raise
```

---

## Testing

### Test Structure

```python
"""Tests for the ticket categorizer."""

import pytest
from ticketinsight.nlp.categorizer import TicketCategorizer
from ticketinsight.nlp.models import TrainingSample


class TestTicketCategorizer:
    """Test suite for the TicketCategorizer class."""

    @pytest.fixture
    def categorizer(self) -> TicketCategorizer:
        """Create a categorizer with test configuration."""
        return TicketCategorizer(
            confidence_threshold=0.5
        )

    @pytest.fixture
    def training_data(self) -> list[TrainingSample]:
        """Create sample training data."""
        return [
            TrainingSample(
                text="My laptop screen is broken",
                category="Hardware",
                subcategory="Display",
            ),
            TrainingSample(
                text="Cannot connect to VPN",
                category="Network",
                subcategory="VPN",
            ),
        ]

    def test_categorizer_trains_successfully(
        self,
        categorizer: TicketCategorizer,
        training_data: list[TrainingSample],
    ) -> None:
        """Verify that training completes without errors."""
        metrics = categorizer.train(training_data)

        assert categorizer.is_trained
        assert metrics.accuracy > 0
        assert len(metrics.classification_report) > 0

    def test_categorizer_predicts_known_category(
        self,
        categorizer: TicketCategorizer,
        training_data: list[TrainingSample],
    ) -> None:
        """Verify prediction on training-like text."""
        categorizer.train(training_data)

        result = categorizer.predict("my monitor is not working")

        assert result.category == "Hardware"
        assert result.confidence >= 0.5

    def test_categorizer_raises_when_not_trained(
        self,
        categorizer: TicketCategorizer,
    ) -> None:
        """Verify that prediction fails when model is not trained."""
        with pytest.raises(ModelNotTrainedError):
            categorizer.predict("test text")

    @pytest.mark.parametrize("text,expected_category", [
        ("screen is broken", "Hardware"),
        ("cannot connect to wifi", "Network"),
        ("password reset", "Access"),
    ])
    def test_categorizer_handles_various_inputs(
        self,
        categorizer: TicketCategorizer,
        training_data: list[TrainingSample],
        text: str,
        expected_category: str,
    ) -> None:
        """Parametrized test for multiple input scenarios."""
        categorizer.train(training_data)
        result = categorizer.predict(text)
        assert result.category == expected_category
```

### Test Categories and Markers

```python
# Unit tests (fast, no external dependencies)
def test_text_preprocessor_removes_html():
    ...

# Integration tests (may use database or test fixtures)
@pytest.mark.integration
def test_full_pipeline_with_database():
    ...

# Slow tests (long-running ML operations)
@pytest.mark.slow
def test_model_training_with_large_dataset():
    ...

# Adapter tests (require mock external services)
@pytest.mark.adapter
def test_servicenow_adapter_pagination():
    ...
```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_nlp/test_categorizer.py

# Specific test class
pytest tests/test_nlp/test_categorizer.py::TestTicketCategorizer

# Specific test
pytest tests/test_nlp/test_categorizer.py::TestTicketCategorizer::test_predict

# Run by marker
pytest -m "not slow"           # Skip slow tests
pytest -m integration          # Only integration tests
pytest -m "adapter or slow"    # Adapter and slow tests

# Parallel execution
pytest -n auto

# With coverage
pytest --cov=src/ticketinsight --cov-report=html --cov-fail-under=80

# Verbose output
pytest -v -s

# Only last-failed tests
pytest --lf

# Stop on first failure
pytest -x
```

### Test Coverage

We aim for the following coverage targets:

| Component | Target |
|-----------|--------|
| API endpoints | 85%+ |
| NLP pipeline | 80%+ |
| ML models | 75%+ |
| Adapters | 80%+ |
| Analytics engine | 80%+ |
| Overall | 80%+ |

### Mocking External Dependencies

```python
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

@pytest.mark.asyncio
async def test_fetch_tickets_with_mock_adapter():
    """Test ticket fetching with a mocked adapter."""

    mock_adapter = AsyncMock(spec=BaseAdapter)
    mock_adapter.name = "test_adapter"
    mock_adapter.fetch_tickets.return_value = iter([
        TicketData(
            ticket_id="TEST001",
            title="Test Ticket",
            description="Test description",
            source_system="test",
        )
    ])

    with patch("ticketinsight.processing.orchestrator.get_adapter", return_value=mock_adapter):
        result = await sync_tickets("test_adapter")

        assert len(result) == 1
        assert result[0].ticket_id == "TEST001"
        mock_adapter.connect.assert_called_once()
        mock_adapter.fetch_tickets.assert_called_once()
```

---

## Documentation

### Docstring Format

Use Google-style docstrings for all public modules, classes, and functions:

```python
def calculate_sla_compliance(
    tickets: list[Ticket],
    sla_definitions: dict[str, SLADefinition],
) -> SLAReport:
    """Calculate SLA compliance for a list of tickets.

    Evaluates each ticket against its priority-specific SLA definition
    to determine response and resolution compliance.

    Args:
        tickets: List of resolved or closed tickets to evaluate.
            Tickets without a resolved_at timestamp are skipped.
        sla_definitions: Mapping of priority names to SLA definitions.
            Each definition includes response_time and resolution_time targets.

    Returns:
        An SLAReport containing overall compliance rates,
        per-priority breakdowns, and a list of breaches.

    Raises:
        ValueError: If sla_definitions is empty or no valid tickets provided.

    Examples:
        >>> definitions = {"High": SLADefinition(response_minutes=30, resolution_hours=8)}
        >>> report = calculate_sla_compliance(tickets, definitions)
        >>> print(report.resolution_compliance_rate)
        0.91
    """
```

### Documentation Updates

When making changes, update the relevant documentation:

| Change Type | Documentation to Update |
|-------------|------------------------|
| New API endpoint | `docs/API_REFERENCE.md` |
| New configuration option | `README.md` (Configuration section) |
| New adapter | `docs/ADAPTER_GUIDE.md` |
| Architecture change | `docs/ARCHITECTURE.md` |
| Deployment change | `docs/DEPLOYMENT_GUIDE.md` |
| Bug fix | `docs/CHANGELOG.md` |
| New feature | `docs/CHANGELOG.md`, relevant docs |

---

## Commit Messages

We follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short description>

<optional longer description>

<optional footer with breaking changes and issues>
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Code style changes (formatting, semicolons) |
| `refactor` | Code refactoring without behavior change |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `chore` | Build process, dependencies, tooling |
| `ci` | CI/CD configuration |
| `revert` | Revert a previous commit |

### Scopes

Common scopes: `api`, `nlp`, `ml`, `adapters`, `analytics`, `processing`,
`database`, `cli`, `config`, `docs`, `docker`

### Examples

```
feat(api): add ticket bulk delete endpoint

Implements DELETE /api/v1/tickets/batch endpoint that accepts
a list of ticket IDs and removes them from the local store.

Closes #142
```

```
fix(adapters): handle ServiceNow pagination cursor expiry

When ServiceNow returns a 400 error with cursor expired message,
the adapter now automatically restarts the sync from the last
known watermark instead of failing.

Fixes #234
```

```
fix(nlp): correct sentiment score normalization

Sentiment scores were not properly normalized to the [-1, 1] range
when using the transformer model, causing all scores to cluster
near 0. This fix applies min-max normalization after prediction.

BREAKING CHANGE: Sentiment scores from previously analyzed tickets
may differ after re-analysis. Run `ticketinsight analyze --all` to
update all historical scores.
```

---

## Pull Requests

### Before Submitting

- [ ] All tests pass: `pytest`
- [ ] Linting passes: `ruff check src/ tests/`
- [ ] Type checking passes: `mypy src/ticketinsight`
- [ ] Code is formatted: `ruff format src/ tests/`
- [ ] New code has test coverage
- [ ] Documentation is updated
- [ ] Changelog is updated
- [ ] Commit messages follow conventions
- [ ] No secrets or credentials in the code

### PR Template

```markdown
## Description
Brief description of the changes in this PR.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring
- [ ] Performance improvement

## Related Issues
Closes #123
Related to #456

## Testing
Describe the testing performed:
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings introduced
- [ ] All tests pass
```

### PR Review Process

1. **Automated checks**: CI pipeline runs tests, linting, type checking
2. **Peer review**: At least one maintainer reviews the code
3. **Feedback**: Reviewer provides constructive feedback
4. **Revision**: Author addresses feedback
5. **Approval**: Maintainer approves the PR
6. **Merge**: Squash merge into `main`

### Review Guidelines for Reviewers

- Focus on correctness, readability, and maintainability
- Point out potential bugs or edge cases
- Suggest improvements, but don't nitpick style (let ruff handle it)
- Be respectful and constructive
- Approve when the PR is good enough, not perfect

---

## Issue Reporting

### Bug Reports

When reporting a bug, please include:

1. **Environment**: OS, Python version, Docker version
2. **Steps to reproduce**: Clear, numbered steps
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Error output**: Full stack trace or error message
6. **Configuration**: Relevant parts of your `config.yaml` (secrets redacted)

### Feature Requests

For feature requests, please describe:

1. **Problem**: What problem are you trying to solve?
2. **Proposed solution**: How would you like it to work?
3. **Alternatives considered**: Other approaches you've thought about
4. **Use case**: How would this feature be used in practice?

---

## Contributor Areas

### Good First Issues

Look for issues labeled `good first issue` on GitHub. These are typically:
- Documentation improvements
- Test additions for existing code
- Small bug fixes with clear reproduction steps
- CLI help text improvements

### Advanced Contributions

| Area | Skills Required | Starting Point |
|------|----------------|----------------|
| **New adapters** | REST APIs, async Python | `src/ticketinsight/adapters/base.py` |
| **NLP improvements** | NLP, scikit-learn, spaCy | `src/ticketinsight/nlp/` |
| **ML models** | ML, feature engineering | `src/ticketinsight/ml/` |
| **Dashboard widgets** | Data visualization, JSON | `src/ticketinsight/analytics/dashboard.py` |
| **API endpoints** | FastAPI, Pydantic | `src/ticketinsight/api/` |

---

## Release Process

The release process is managed by maintainers:

1. Update version in `pyproject.toml`
2. Update `docs/CHANGELOG.md` with release notes
3. Create a GitHub release with tag
4. Build and publish Docker image
5. Publish to PyPI
6. Update documentation

Thank you for contributing to TicketInsight Pro!
