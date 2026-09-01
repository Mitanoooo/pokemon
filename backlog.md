# Backlog

Items deferred from design sessions. Pick up when the relevant area is under active work.

---

## Scraper improvements pass

### Per-item URL selectors — coverage gaps
- `karukortti.fi` has no `product_url` selector at all (active site).
- Several selectors point at non-anchor elements so `.get("href")` silently returns `""`.
- Most shops emit relative hrefs; the URL-fixup in the scraper does `urljoin` but it should be verified against each config.
- **Action:** audit all 40 `site_configs/*.json` for `product_url` selector correctness and relativeness; add missing selectors; add a sanity test that every active config produces at least one non-empty URL in a test scrape.

### Two more sites at zero readings (found during issue 04's verification run)
- `karukortti.fi`: 8 products parse but none priced. The shop prints dot-decimal (`€359.95`) and the config has no `"decimal_separator": "dot"`, so prices come out as 35995.00 and the suspicious-price guard drops them. Missed when issue 03 moved the dot-decimal site set out of `price_parser` into the configs.
- `swagykarp.fi`: the category URL 302s into a CrowdHandler waiting room (`wait.crowdhandler.com/...`) that returns a 12 KB queue page with no products.
- **Action:** add `"decimal_separator": "dot"` to `karukortti.fi.json` and re-scrape to confirm; decide whether `swagykarp.fi` gets `"disabled": true` or a queue-aware fetch. Neither site is in issue 04's scope, and neither is affected by its changes.

### Stock detection — site configs
Superseded by the tracker refocus. `stock_mode` is gone; configs carry an
`availability` block and 23 of 40 have one after ticket 15's mechanical
migration. Getting the remaining 17 tracked, and fixing the badge_text sites
where a preorder badge still reads as in stock, is tickets 16 to 18 in
`.wayfinder/`.
