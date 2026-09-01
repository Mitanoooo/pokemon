# 02 — Scraper: run tracking and listings persistence

**What to build:** Every scraper invocation is recorded as a run, and every product the scraper sees — including items whose price can't be parsed — is upserted into `listings` with a direct item URL, first-seen and last-seen timestamps, and the current run's id. This is the foundation for both the inline listings panel and the updates feed; without it those features have no data to show.

Concretely:

- `run_all_sites()` creates a `scrape_runs` row at the start and stamps `finished_at` when all sites are done. The `run_id` is threaded into every `run_site()` call.
- Inside `run_site()`, before the existing `valid = [price is not None]` filter, every product returned by `scrape_page()` (including price-less ones) is upserted into `listings`. Relative `product_url` values are resolved to absolute using the site's `source_url` as the base. `first_seen_at` is set only on the first insert; `last_seen_at` and `last_run_id` are updated on every upsert. `product_id` is resolved from `name_mappings` at upsert time (same lookup the existing `write_readings` does).
- Price-less products still do not go into `price_readings` — the existing filter is preserved for that table. Only the `listings` upsert scope widens.
- `price_readings` inserts gain the `run_id`.
- `db.save_mapping()` is extended to backfill `listings.product_id` for all rows whose `raw_name` matches, alongside the existing `price_readings.product_id` backfill.

New `scraper/db.py` functions: `start_run`, `finish_run`, `get_listing_state` (returns current `listings` rows for a site keyed by `raw_name` — needed by the event-diff logic in ticket 03), `upsert_listing`.

**Blocked by:** 01 — Schema migration.

**Status:** ready-for-agent

- [ ] Running the scraper produces a row in `scrape_runs` with both `started_at` and `finished_at` populated.
- [ ] After a scraper run, `listings` contains one row per distinct `(site_id, raw_name)` pair observed, including pairs where no price was parsed.
- [ ] `listings.product_url` is an absolute URL for every listing where the site config has a `product_url` selector and the element has an `href`; relative hrefs have been resolved against the site's `source_url`.
- [ ] `listings.first_seen_at` does not change on subsequent runs for the same `(site_id, raw_name)` pair.
- [ ] `listings.last_seen_at` and `listings.last_run_id` are updated on every run that sees the listing.
- [ ] `price_readings` rows written after this change carry the correct `run_id`; existing rows retain `run_id = NULL`.
- [ ] `db.save_mapping()` updates `listings.product_id` for all matching `raw_name` rows.
- [ ] `tests/test_db.py` covers: `upsert_listing` on a new pair sets `first_seen_at = last_seen_at`; `upsert_listing` on a known pair updates `last_seen_at` without changing `first_seen_at`; `upsert_listing` with `price=None` stores `latest_price = NULL` without error; `save_mapping` backfills `listings.product_id`.
- [ ] `tests/test_runner.py` covers: `run_site()` creates a `scrape_runs` row; `run_site()` upserts a `listings` row for a price-less product; that price-less product does not appear in `price_readings`; `price_readings` rows carry the `run_id`.
- [ ] `python -m pytest tests/` passes.
