"""
Tests for utility helper functions.
"""
import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from ticketinsight.utils.helpers import (
    sanitize_text, normalize_priority, normalize_status, parse_date,
    chunk_list, calculate_hash, time_ago, truncate, slugify, retry_on_failure
)


class TestSanitizeText:
    def test_removes_html_tags(self):
        result = sanitize_text('<script>alert("xss")</script>Hello world')
        assert '<script>' not in result
        assert 'Hello world' in result

    def test_removes_html_entities(self):
        result = sanitize_text('Hello &amp; World &lt;br&gt;')
        assert '&amp;' not in result

    def test_normalizes_whitespace(self):
        result = sanitize_text('hello    world\n\n\ntest')
        assert 'hello world test' == result

    def test_handles_empty_string(self):
        assert sanitize_text('') == ''

    def test_handles_none(self):
        assert sanitize_text(None) == ''

    def test_strips_leading_trailing_whitespace(self):
        assert sanitize_text('  hello  ') == 'hello'

    def test_handles_unicode(self):
        result = sanitize_text('Hello \u2013 World \u2014 Test')
        assert 'Hello' in result


class TestNormalizePriority:
    def test_standard_priorities(self):
        assert normalize_priority('critical') == 'Critical'
        assert normalize_priority('high') == 'High'
        assert normalize_priority('medium') == 'Medium'
        assert normalize_priority('low') == 'Low'

    def test_numeric_priorities(self):
        assert normalize_priority('1') == 'Critical'
        assert normalize_priority('2') == 'High'
        assert normalize_priority('3') == 'Medium'
        assert normalize_priority('4') == 'Low'

    def test_p_format(self):
        assert normalize_priority('P1') == 'Critical'
        assert normalize_priority('P2') == 'High'
        assert normalize_priority('P3') == 'Medium'
        assert normalize_priority('P4') == 'Low'

    def test_case_insensitive(self):
        assert normalize_priority('CRITICAL') == 'Critical'
        assert normalize_priority('High') == 'High'
        assert normalize_priority('MEDIUM') == 'Medium'
        assert normalize_priority('Low') == 'Low'

    def test_with_spaces(self):
        assert normalize_priority('p 1') == 'Critical'
        assert normalize_priority('P 2') == 'High'

    def test_unknown_priority(self):
        assert normalize_priority('unknown') in ['Medium', 'Low']

    def test_empty_string(self):
        result = normalize_priority('')
        assert result in ['Medium', 'Low', '']


class TestNormalizeStatus:
    def test_standard_statuses(self):
        assert normalize_status('open') == 'Open'
        assert normalize_status('in progress') == 'In Progress'
        assert normalize_status('resolved') == 'Resolved'
        assert normalize_status('closed') == 'Closed'

    def test_aliases(self):
        assert normalize_status('new') == 'Open'
        assert normalize_status('active') == 'In Progress'
        assert normalize_status('done') == 'Closed'
        assert normalize_status('completed') == 'Closed'
        assert normalize_status('on hold') == 'On Hold'
        assert normalize_status('pending') == 'On Hold'

    def test_numeric_states(self):
        assert normalize_status('1') == 'Open'
        assert normalize_status('2') == 'In Progress'
        assert normalize_status('6') == 'Resolved'
        assert normalize_status('7') == 'Closed'

    def test_case_insensitive(self):
        assert normalize_status('OPEN') == 'Open'
        assert normalize_status('RESOLVED') == 'Resolved'


class TestParseDate:
    def test_iso_format(self):
        result = parse_date('2024-01-15T09:30:00')
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_date_only(self):
        result = parse_date('2024-01-15')
        assert result is not None
        assert result.year == 2024

    def test_none_input(self):
        result = parse_date(None)
        assert result is None

    def test_empty_string(self):
        result = parse_date('')
        assert result is None

    def test_unix_timestamp(self):
        result = parse_date('1705312200')
        assert result is not None


class TestChunkList:
    def test_even_chunks(self):
        result = chunk_list([1, 2, 3, 4], 2)
        assert result == [[1, 2], [3, 4]]

    def test_uneven_chunks(self):
        result = chunk_list([1, 2, 3, 4, 5], 2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_empty_list(self):
        assert chunk_list([], 3) == []

    def test_chunk_size_larger_than_list(self):
        result = chunk_list([1, 2], 5)
        assert result == [[1, 2]]

    def test_single_element(self):
        result = chunk_list([1], 3)
        assert result == [[1]]

    def test_preserves_all_elements(self):
        original = list(range(10))
        chunks = chunk_list(original, 3)
        flattened = [item for chunk in chunks for item in chunk]
        assert flattened == original


class TestCalculateHash:
    def test_deterministic(self):
        assert calculate_hash('hello') == calculate_hash('hello')

    def test_different_inputs(self):
        assert calculate_hash('hello') != calculate_hash('world')

    def test_returns_string(self):
        assert isinstance(calculate_hash('test'), str)

    def test_consistent_length(self):
        h1 = calculate_hash('a')
        h2 = calculate_hash('abc')
        assert len(h1) == len(h2)

    def test_handles_empty_string(self):
        result = calculate_hash('')
        assert isinstance(result, str)
        assert len(result) > 0


class TestTimeAgo:
    def test_seconds(self):
        result = time_ago(datetime.now() - timedelta(seconds=30))
        assert isinstance(result, str)

    def test_minutes(self):
        result = time_ago(datetime.now() - timedelta(minutes=5))
        assert isinstance(result, str)
        assert 'minute' in result.lower()

    def test_hours(self):
        result = time_ago(datetime.now() - timedelta(hours=3))
        assert isinstance(result, str)
        assert 'hour' in result.lower()

    def test_days(self):
        result = time_ago(datetime.now() - timedelta(days=2))
        assert isinstance(result, str)
        assert 'day' in result.lower()

    def test_future_time(self):
        result = time_ago(datetime.now() + timedelta(seconds=10))
        assert isinstance(result, str)


class TestTruncate:
    def test_short_text(self):
        assert truncate('hello', 100) == 'hello'

    def test_long_text(self):
        result = truncate('hello world this is a test', 10)
        assert len(result) <= 15  # with ellipsis

    def test_at_word_boundary(self):
        result = truncate('hello world test', 12)
        assert result is not None

    def test_empty_string(self):
        assert truncate('', 10) == ''

    def test_none_input(self):
        assert truncate(None, 10) == '' or truncate(None, 10) is None


class TestSlugify:
    def test_basic(self):
        assert slugify('Hello World') == 'hello-world'

    def test_special_chars(self):
        result = slugify('Hello! @World# $Test')
        assert 'hello' in result
        assert 'world' in result
        assert 'test' in result

    def test_multiple_spaces(self):
        assert slugify('Hello   World') == 'hello-world'

    def test_empty_string(self):
        result = slugify('')
        assert isinstance(result, str)


class TestRetryOnFailure:
    def test_succeeds_first_try(self):
        call_count = 0

        @retry_on_failure(retries=3, delay=0.01)
        def success_func():
            nonlocal call_count
            call_count += 1
            return 'success'

        result = success_func()
        assert result == 'success'
        assert call_count == 1

    def test_succeeds_after_retry(self):
        call_count = 0

        @retry_on_failure(retries=3, delay=0.01, exceptions=(ValueError,))
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return 'success'

        result = flaky_func()
        assert result == 'success'
        assert call_count == 3

    def test_exceeds_max_retries(self):
        @retry_on_failure(retries=2, delay=0.01, exceptions=(ValueError,))
        def always_fail():
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            always_fail()
