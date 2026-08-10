from urllib.parse import urlparse


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

    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    urls = [source_url]
    for page in range(2, max_pages + 1):
        raw = pattern.format(page=page)
        if raw.startswith("/"):
            urls.append(base + raw)
        else:
            urls.append(raw)
    return urls


def _offset(source_url: str, pagination: dict) -> list[str]:
    pattern: str = pagination["url_pattern"]
    max_pages: int = pagination.get("max_pages", 1)

    urls = [source_url]
    for page in range(2, max_pages + 1):
        offset = (page - 1) * 60
        urls.append(source_url + pattern.format(offset=offset))
    return urls


