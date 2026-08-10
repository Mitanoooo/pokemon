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


def fetch(url: str, config: Optional[dict] = None) -> Optional[str]:
    if config and config.get("fetch_method") == "playwright":
        raise NotImplementedError("playwright fetch is not yet implemented")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None
