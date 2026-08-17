from urllib.parse import urljoin


def is_paginated(config: dict) -> bool:
    """True when the config declares more pages than the source_url itself."""
    return (config.get("pagination") or {}).get("type", "none") != "none"


def paginate(config: dict) -> "list[str]":
    source_url: str = config["source_url"]
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

    urls = [source_url]
    for page in range(2, max_pages + 1):
        offset = (page - 1) * 60
        urls.append(source_url + pattern.format(offset=offset))
    return urls


