# 14 — Strip mapping, products, thresholds and email

## Question

Delete every code path that depended on canonical product identity, thresholds, price history or email. Nothing here is a behaviour change to keep, it is removal. See [spec](../spec-tracker-refocus.md) → "Solution" and "Out of Scope".

**App pages deleted** and removed from `app/main.py`'s nav dict:
`app/views/products.py`, `thresholds.py`, `mappings.py`, `unknowns.py`, `categories.py`.
Nav afterwards: Updates, By site, Search, Site health (the first three are built in ticket 20; leave placeholders if 20 has not landed).

**`scraper/db.py` functions deleted:**
`get_products_summary`, `get_product_price_history`, `get_latest_price_per_site`, `get_thresholds_for_all_products`, `get_products_below_threshold`, `save_mapping`, `_resolve_product_id`, `write_readings`, and the mapping-review queries. `upsert_listing` loses its `_resolve_product_id` call and its `product_id` column.

**Scripts and prompts deleted:**
`scripts/apply_batch.py`, `scripts/update_catalog.py`, `scripts/extract_catalog.py`, `scripts/calibration_candidates.py`, `scripts/setup_email.py`, `scraper/digest.py`, `copilot_prompts/llm_normalise.md`, `llm_batch_normalise.md`, `llm_calibrate.md`, `scrape_catalog.md`.

**Data files deleted:**
`cardmarket_catalogue.json`, `catalog_scrape.json`, `catalog_*.txt` (8), `draft_mappings.json`, `calibration_examples.md`, `batch_0*.csv` (27, untracked).

**Cron:** remove the digest line from `deploy/crontab.txt` and from the server's crontab. The scraper line is unchanged.

**Tests deleted:** `test_apply_batch.py`, `test_calibration_candidates.py`, `test_calibration_examples.py`, `test_extract_catalog.py`, `test_digest.py`, `test_setup_email.py`, `test_writeback_db.py`, `test_app_db.py`. `test_db.py` is trimmed to the surviving functions (ticket 20 adds the new query tests).

**Docs:** `deploy/README.md` loses the mapping-pass section, the digest section and the schema-v3 migration block; it gains a pointer to `scripts/rebuild_db.py`. `.wayfinder/spec-accuracy-overhaul.md` and `spec-interface-improvements.md` stay as history.

Verification: `grep -ril "name_mappings\|cardmarket\|price_readings\|threshold\|digest" app scraper scripts tests deploy` returns only the archived specs and this ticket set.

## Outcome

Done, with three additions the ticket's file list did not name:

- `scraper/normaliser.py` and `docs/normaliser_example_input.json` are deleted too. Nothing imported the module and it wrote to `product_aliases` and `price_readings`, so it was dead mapping code that would have failed the verification grep.
- `upsert_listing` and `get_listing_state` move from `latest_in_stock` to `availability`, mapping the parser's current `True` / `False` / `None` to `in_stock` / `out_of_stock` / `unknown`, and overwriting on every sighting per the spec. Ticket 13's `schema.sql` has no `latest_in_stock` column, so without this the runner could not write at all. Ticket 15 replaces the boolean argument with the four-state parser result.
- `_build_update_events` writes `price_drop` / `price_rise` instead of `price_change`, for the same reason: the new `updates.event_type` CHECK rejects `price_change`. The rest of the event rework stays with ticket 19.

`_latest_priced_sighting_per_name` went with `write_readings`; the health check it fed is now `_priced_name_count`.

Remaining verification-grep hits are all legitimate: `price_threshold` (the price-delta epsilon in the runner), `hmac.compare_digest` in the deploy server, the old table names in `scripts/rebuild_db.py`, which has to read them, one README line saying they are gone, and shop HTML in `tests/fixtures/`.

`.env.example` keeps its `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `DIGEST_TO` keys by decision — nothing reads them, and they are a record for the day email comes back on top of `updates`.

The digest line is gone from `deploy/crontab.txt` and from the server. It lived in the `pokemon` user's crontab, not root's, which is where to look next time; `deploy/crontab.txt` is now installed verbatim as that user's crontab, and the old five-line version is backed up at `/root/crontab.pokemon.pre-refocus.bak` on `65.21.178.63`.

**Status: DONE**

Blocking: 20
Blocked by: 13 (needs the new `schema.sql` for test fixtures; both deploy together)
