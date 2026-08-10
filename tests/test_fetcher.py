"""Tests for scraper.fetcher.fetch."""
from unittest.mock import MagicMock, patch

import pytest

from scraper.fetcher import fetch


def _mock_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_returns_html_on_success():
    with patch("scraper.fetcher.requests.get", return_value=_mock_response("<html>ok</html>")):
        assert fetch("https://example.com") == "<html>ok</html>"


def test_fetch_returns_none_on_connection_error():
    with patch("scraper.fetcher.requests.get", side_effect=OSError("refused")):
        assert fetch("https://example.com") is None


def test_fetch_returns_none_on_http_error():
    mock = _mock_response("")
    mock.raise_for_status.side_effect = Exception("404")
    with patch("scraper.fetcher.requests.get", return_value=mock):
        assert fetch("https://example.com") is None


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
