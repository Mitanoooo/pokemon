# 02 — Improve scraper observability

**What to build:** Two gaps make failing sites hard to diagnose. First, the fetcher catches all exceptions and returns None, so `last_error` in the site health table always reads "fetch returned None" regardless of whether the cause was a 403, a timeout, or a DNS failure. Log and surface the HTTP status code and original exception type so the health page gives actionable information. Second, when a run finishes all configured pages and the final page still contained products, there are likely more pages being silently skipped — no signal exists today. Emit a warning log line in this case so configs with an undercount `max_pages` are self-reporting.

**Blocked by:** None — can start immediately.

**Status:** done

- [ ] `last_error` for an HTTP error shows the status code (e.g. "HTTP 403 for https://…")
- [ ] `last_error` for a network/timeout error shows the exception type and message
- [ ] A `WARNING` log line is emitted when the final paginated page returned products (potential `max_pages` undercount)
- [ ] Sites that succeed are unaffected
