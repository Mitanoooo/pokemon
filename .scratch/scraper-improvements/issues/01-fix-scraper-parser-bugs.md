# 01 — Fix scraper/paginator bugs

**What to build:** Two concrete bugs are silently dropping data. First, the paginator generates bare `?page=2` strings for query-string pagination patterns (e.g. Blockhouse Games), which are never resolved against the source URL — fetch returns None and the site logs a failure. Fix the paginator so query-string-only patterns are resolved via `urljoin(source_url, raw)` rather than treated as absolute URLs. Second, KaruKortti's product containers are `<a>` tags, so there is no separate anchor to point a `product_url` selector at — the config correctly leaves it null, but `_extract_url` returns an empty string instead of the container's own `href`. Fix the URL extractor to fall back to the container element's `href` when no selector is configured and the container is an anchor.

**Blocked by:** None — can start immediately.

**Status:** done

- [ ] Paginator resolves `?page=N` patterns correctly via `urljoin`; Blockhouse Games fetches both pages without error
- [ ] `_extract_url` returns the container's `href` when `product_url` selector is null and the container is an `<a>` element
- [ ] KaruKortti listings carry a non-empty `product_url` after a scrape
- [ ] Existing paginator behaviour for absolute URLs and `/path/{page}` patterns is unchanged
