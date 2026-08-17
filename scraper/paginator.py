from typing import Optional
from urllib.parse import urljoin


def is_paginated(config: dict) -> bool:
    """True when the config declares more pages than the source_url itself."""
    return (config.get("pagination") or {}).get("type", "none") != "none"


def source_urls(config: dict) -> "list[str]":
    """Every entry URL of one site.

    Sites whose products are split across category pages list them in
    "source_urls"; everything else carries a single "source_url".
    """
    urls = config.get("source_urls")
    if urls:
        return list(urls)
    return [config["source_url"]]


def paginate(config: dict, source_url: Optional[str] = None) -> "list[str]":
    """Page URLs for one of the site's entry URLs (the first one by default)."""
    if source_url is None:
        source_url = source_urls(config)[0]
    pagination: dict = config.get("pagination", {})
    ptype: str = pagination.get("type", "none")

    if ptype == "none":
        return [source_url]

    if ptype == "url_pattern":
        return _url_pattern(source_url, pagination)

    if ptype == "offset":
        return _offset(source_url, pagination)

    return [source_url]


def _url_pattern(source_url: str, pagination: dict) -> list[str]:
    pattern: str = pagination["url_pattern"]
    max_pages: int = pagination.get("max_pages", 1)

    # urljoin covers all three pattern shapes in the configs: absolute URLs pass
    # through, "/path/{page}" gets the source's scheme+host, and query-only
    # "?page={page}" (Blockhouse Games) keeps the source path.
    urls = [source_url]
    for page in range(2, max_pages + 1):
        urls.append(urljoin(source_url, pattern.format(page=page)))
    return urls


def _offset(source_url: str, pagination: dict) -> list[str]:
    pattern: str = pagination["url_pattern"]
    max_pages: int = pagination.get("max_pages", 1)
    page_size: int = pagination.get("page_size", 60)

    urls = [source_url]
    for page in range(2, max_pages + 1):
        offset = (page - 1) * page_size
        urls.append(source_url + pattern.format(offset=offset))
    return urls


