from typing import Optional

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
}

# urllib3's DNS/SSL messages run to 300+ chars; keep last_error readable.
_MAX_CAUSE_CHARS = 160


class FetchError(Exception):
    """A page could not be fetched.

    The message names the cause — "HTTP 403 for <url>" or
    "<ExceptionType>: <message> for <url>" — because run_site records it in
    the sites.last_error column the health page reads.
    """


def fetch(url: str, config: Optional[dict] = None) -> str:
    """Fetch a page as text, or raise FetchError describing why it failed."""
    if config and config.get("fetch_method") == "playwright":
        raise NotImplementedError("playwright fetch is not yet implemented")

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
    except Exception as exc:
        raise FetchError(f"{type(exc).__name__}: {_trim(str(exc))} for {url}") from exc

    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} for {url}")

    return resp.text


def _trim(cause: str) -> str:
    if len(cause) <= _MAX_CAUSE_CHARS:
        return cause
    return cause[:_MAX_CAUSE_CHARS] + "…"
