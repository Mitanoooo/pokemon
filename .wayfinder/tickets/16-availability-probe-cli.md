# 16 — Availability probe CLI

## Question

Write `scraper/probe.py` so pinning down a site's availability badges is a two-minute loop instead of guesswork. Operator tool, not part of a scrape run. See [spec](../spec-tracker-refocus.md) → "Probe tool".

```
python -m scraper.probe site_configs/tcgkauppa.fi.json [--url N] [--html-file page.html] [--limit 5]
python -m scraper.probe --all
```

Single-site mode fetches page 1 of each of the site's URLs (or reads `--html-file`), runs the config's `product_container` selector, and prints per site:

- distinct container class lists with counts
- distinct text of the configured `availability.selector` plus heuristic candidates: `[class*=stock]`, `[class*=avail]`, `[class*=badge]`, `[class*=saatav]`, `[class*=ennakko]`
- distinct `data-*` attribute values whose name contains `avail` or `stock`
- the availability split the current config produces, with the unknown share as a percentage
- up to `--limit` sample raw names per resolved state, so a wrong mapping is obvious by eye

`--all` loops every non-disabled config and prints one line per site: name, listings parsed, split by state, unknown share, configured forms. That output is the acceptance check for ticket 18. It respects the same 1-4s inter-fetch jitter as the scraper.

`--html-file` exists so the tool works against saved fixtures with no network, which is also how it gets tested.

**Tests:** one test that `--html-file` against an existing fixture in `tests/fixtures/` reports the expected split and badge census. No network in tests.

**Status: OPEN**

Blocking: 18
Blocked by: 15
