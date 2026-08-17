"""Tests for scraper.fetcher.fetch."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from scraper.fetcher import FetchError, fetch


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.status_code = status_code
    return r


def test_fetch_returns_html_on_success():
    with patch("scraper.fetcher.requests.get", return_value=_mock_response("<html>ok</html>")):
        assert fetch("https://example.com") == "<html>ok</html>"


def test_fetch_connection_error_names_exception_type_and_message():
    with patch("scraper.fetcher.requests.get", side_effect=OSError("refused")):
        with pytest.raises(FetchError) as exc_info:
            fetch("https://example.com")
    text = str(exc_info.value)
    assert "OSError" in text
    assert "refused" in text
    assert "https://example.com" in text


def test_fetch_timeout_names_exception_type():
    with patch("scraper.fetcher.requests.get", side_effect=requests.Timeout("timed out")):
        with pytest.raises(FetchError) as exc_info:
            fetch("https://example.com")
    assert "Timeout" in str(exc_info.value)


def test_fetch_trims_a_very_long_cause_but_keeps_type_and_url():
    long_cause = "x" * 500
    with patch("scraper.fetcher.requests.get", side_effect=OSError(long_cause)):
        with pytest.raises(FetchError) as exc_info:
            fetch("https://example.com/shop")
    text = str(exc_info.value)
    assert len(text) < 250
    assert text.startswith("OSError: ")
    assert text.endswith("for https://example.com/shop")


def test_fetch_raises_with_status_code_on_http_error():
    with patch("scraper.fetcher.requests.get", return_value=_mock_response("", status_code=403)):
        with pytest.raises(FetchError) as exc_info:
            fetch("https://example.com/shop")
    text = str(exc_info.value)
    assert "HTTP 403" in text
    assert "https://example.com/shop" in text


def test_fetch_success_does_not_raise_for_2xx_and_3xx():
    for status in (200, 301):
        with patch("scraper.fetcher.requests.get",
                   return_value=_mock_response("<html>ok</html>", status_code=status)):
            assert fetch("https://example.com") == "<html>ok</html>"


def test_fetch_sends_browser_user_agent():
    with patch("scraper.fetcher.requests.get", return_value=_mock_response("")) as m:
        fetch("https://example.com")
    assert "Mozilla" in m.call_args[1]["headers"]["User-Agent"]


def test_fetch_sends_accept_language_fi():
    with patch("scraper.fetcher.requests.get", return_value=_mock_response("")) as m:
        fetch("https://example.com")
    assert "fi-FI" in m.call_args[1]["headers"]["Accept-Language"]


def test_fetch_playwright_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        fetch("https://example.com", config={"fetch_method": "playwright"})
