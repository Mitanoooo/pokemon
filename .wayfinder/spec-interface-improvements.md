# Spec — Interface Improvements (Sorting, Item Links, Listings Panel, Updates Feed)

## Problem Statement

The products view is unsortable and slow to scan: rows are fixed in price order within hard-coded category groups, so finding the cheapest item overall requires reading every group. Clicking a site name opens the shop homepage, not the specific product page, forcing a second manual search. Reviewing all listings for a product requires navigating away to a detail page — there is no way to peek at them from the list. And nothing records what changed between scraper runs: price drops, new listings, and restocks leave no trace, so the only way to notice them is to stare at the table long enough to remember yesterday's numbers.

## Solution

Four focused improvements delivered together because they share a common foundation — a new `listings` table that tracks per-(site, product) state across runs, and a `scrape_runs` table that gives the scraper a run identity.

1. **Sortable products table.** Replace the hand-rolled per-category grid with a native dataframe. Every column is click-sortable. Category becomes a filter widget rather than a fixed subheader.

2. **Direct item links.** The scraper already extracts per-item URLs but throws them away. Store them in `listings` and surface them in the products table as the primary link, falling back to the site homepage where the URL is missing.

3. **Inline listings panel.** Clicking a row in the products table opens a panel below the table showing all listings for that product: site, price, stock status, direct link, and last seen. The existing detail page (with its price-history chart) is preserved and reachable from the panel.

4. **Updates feed.** The scraper writes a materialised `updates` table at the end of each run, recording price changes, new listings, and restock events. A new Updates page in the app surfaces this feed with per-event mark-as-read and a mapped/unmapped toggle.

## User Stories

1. As the operator, I want to click a column header in the products table to sort by that column, so that I can instantly see the cheapest item across all categories without reading every group.
2. As the operator, I want to click the lowest-price link in the products table and land directly on the product page at that shop, so that I can check the listing without a second search.
3. As the operator, I want the products table to fall back to the site homepage link where a direct item URL is not available, so that I always have at least some link to click.
4. As the operator, I want to filter the products table by category, so that I can narrow the view to a category I care about while still being able to sort within it.
5. As the operator, I want to click a product row and see all its current listings in a panel below the table, so that I can compare prices across shops without leaving the products view.
6. As the operator, I want each listing in the panel to show the site name, price, stock status, direct item link, and when it was last seen, so that I have everything I need to decide whether to buy.
7. As the operator, I want the listings panel to include an "Open detail page" button, so that I can navigate to the full price-history chart when I want more context.
8. As the operator, I want the detail page to remain unchanged, so that existing bookmarks and habits are not disrupted.
9. As the operator, I want an Updates page in the sidebar, so that I can see what changed since the last scraper run without comparing tables manually.
10. As the operator, I want price-change events to appear in the updates feed whenever the latest price for a listing differs from its previous price by any amount, so that I never miss a price movement.
11. As the operator, I want new-listing events to appear in the updates feed the first time a (site, raw_name) pair is seen, so that I know when a shop stocks a product for the first time.
12. As the operator, I want back-in-stock events to appear in the updates feed when a listing transitions from out-of-stock to in-stock, so that I can act quickly when a sought item becomes available.
13. As the operator, I want the updates feed to default to showing only events for mapped products, so that raw-name churn from unmapped listings does not drown out the events I care about.
14. As the operator, I want a toggle to include unmapped listings in the updates feed, so that I can spot new listings that need mapping before they are missed.
15. As the operator, I want to mark individual update entries as read, so that I can track which changes I have already acted on.
16. As the operator, I want a "mark all read" action, so that I can clear the feed after reviewing it in bulk.
17. As the operator, I want update entries to be automatically pruned after 30 days, so that the updates table does not grow unboundedly.
18. As the operator, I want each update entry to show the site name, product name (canonical if mapped, raw_name otherwise), event type, old and new values, and the time of the run, so that I have enough context to act without clicking through.
19. As the operator, I want the scraper to record a run start and end time for every `run_all_sites` invocation, so that updates are traceable to a specific run.
20. As the operator, I want no-price sightings (products the scraper sees but cannot parse a price for) to be tracked in `listings` without entering `price_readings`, so that their reappearance does not generate spurious new-listing events.
21. As the operator, I want back-in-stock events only for sites that have a configured `stock_mode`, so that sites with unknown stock status do not generate noisy or incorrect restock alerts.

## Implementation Decisions

### New tables

**`scrape_runs`** — one row per `run_all_sites()` invocation.

```
id           INTEGER PRIMARY KEY AUTOINCREMENT
started_at   TEXT NOT NULL
finished_at  TEXT
```

**`listings`** — one row per distinct `(site_id, raw_name)` pair ever seen. Upserted on every sighting, including sightings with no parseable price.

```
site_id          INTEGER NOT NULL REFERENCES sites(id)
raw_name         TEXT NOT NULL
PRIMARY KEY (site_id, raw_name)
product_id       INTEGER REFERENCES cardmarket_products(id)
product_url      TEXT
first_seen_at    TEXT NOT NULL
last_seen_at     TEXT NOT NULL
last_run_id      INTEGER REFERENCES scrape_runs(id)
latest_price     REAL              -- nullable; NULL if no parseable price ever seen
latest_currency  TEXT
latest_in_stock  INTEGER
```

`product_id` mirrors `price_readings.product_id`: resolved from `name_mappings` at upsert time and updated whenever a mapping changes (same backfill pattern as `save_mapping`).

**`updates`** — materialised event log, pruned at 30 days.

```
id          INTEGER PRIMARY KEY AUTOINCREMENT
run_id      INTEGER NOT NULL REFERENCES scrape_runs(id)
site_id     INTEGER NOT NULL REFERENCES sites(id)
raw_name    TEXT NOT NULL
product_id  INTEGER REFERENCES cardmarket_products(id)
event_type  TEXT NOT NULL CHECK(event_type IN ('price_change','new_listing','back_in_stock'))
old_value   TEXT    -- previous price (as string) for price_change; NULL for new_listing
new_value   TEXT    -- new price; 'in_stock' for back_in_stock; price for new_listing (or NULL)
created_at  TEXT NOT NULL DEFAULT (datetime('now'))
seen        INTEGER NOT NULL DEFAULT 0
```

### Changes to existing tables

- `price_readings`: add `run_id INTEGER REFERENCES scrape_runs(id)`. Existing rows get `NULL` for this column. `price` remains `NOT NULL` — no-price sightings are absorbed by `listings`, not `price_readings`.
- `schema.sql` updated to match all new DDL.

### Scraper changes — `scraper/runner.py`

`run_site()` gains three new responsibilities around the existing fetch-parse-write loop:

1. **Run record**: `scrape_runs` row created at the start of `run_all_sites()`; `finished_at` stamped after all sites complete. The `run_id` is threaded into `run_site()` and written on every `price_readings` insert.

2. **Listings upsert**: before the existing `valid = [...]` filter, every product returned by `scrape_page()` (including price-less ones) is upserted into `listings`. `product_url` is stored; relative URLs are resolved to absolute using the site's `source_url` as the base (Python `urllib.parse.urljoin`). `first_seen_at` is set only on insert; `last_seen_at` and `last_run_id` are updated on every upsert.

3. **Update event generation**: after the listings upsert, the runner diffs the new state against the previous state (captured from `listings` before the upsert) and writes events to `updates`. Event rules:
   - `new_listing`: `first_seen_at` was just created (i.e., no prior row existed).
   - `price_change`: previous `latest_price` is not NULL, new price is not NULL, and `abs(new - old) >= 0.01`.
   - `back_in_stock`: previous `latest_in_stock = 0` and new `in_stock = 1`; only emitted for sites where the config has a `stock_mode` other than `None`/`'unknown'`.

No `listing_gone` event is emitted. `listings.last_seen_at` drifts naturally when a listing stops appearing.

Pruning of `updates` rows older than 30 days runs at the end of each `run_all_sites()` call.

### New `scraper/db.py` functions

- `start_run(conn) -> int` — inserts into `scrape_runs`, returns `run_id`.
- `finish_run(conn, run_id)` — stamps `finished_at`.
- `get_listing_state(conn, site_id) -> dict[str, dict]` — returns the current `listings` rows for a site, keyed by `raw_name`, for diffing before upsert.
- `upsert_listing(conn, site_id, raw_name, product_url, price, currency, in_stock, run_id)` — insert-or-update `listings`.
- `write_updates(conn, events: list[dict])` — bulk-inserts into `updates`.
- `prune_updates(conn, days=30)` — deletes `updates` rows older than N days.
- `get_updates(conn, mapped_only: bool) -> list[dict]` — returns unseen updates, newest first, optionally filtered to rows where `product_id IS NOT NULL`.
- `mark_updates_seen(conn, ids: list[int])` — sets `seen = 1` for given ids.
- `mark_all_updates_seen(conn)` — sets `seen = 1` for all rows.

### Products view — `app/views/products.py`

The hand-rolled `st.columns` loop and per-category `st.subheader` grouping are replaced by a single `st.dataframe` call using `column_config`.

Columns in the dataframe:

| Column | Type | Notes |
|---|---|---|
| Name | `TextColumn` | canonical name |
| Category | `TextColumn` | sortable; also drives a selectbox filter above the table |
| Lowest price | `NumberColumn` | format `%.2f` |
| Item link | `LinkColumn` | `product_url` from `listings` for the cheapest site; falls back to `sites.url` |
| In stock | `TextColumn` | e.g. `"3 sites"` |
| Last updated | `TextColumn` | truncated to minute |

`column_config.LinkColumn` is used for the Item link column so the cell renders as a clickable anchor.

`st.dataframe` is called with `selection_mode="single-row"` and `on_select="rerun"`. When a row is selected, a listings panel renders immediately below the dataframe. The panel shows one row per site with columns: site name, price, stock, item link (`LinkColumn`), and last seen. Below the panel rows, a single `st.button("Open detail page →")` pushes `selected_product_id` into session state and calls `st.rerun()` to navigate to the existing detail view.

`get_products_summary` is updated to join `listings` (on `site_id` + cheapest site's `raw_name`) to surface `product_url` alongside the existing fields.

### New Updates view — `app/views/updates.py`

Accessible from the sidebar as "Updates". Renders:

- A toggle ("Show unmapped") that switches between `mapped_only=True` and `mapped_only=False` when calling `get_updates`.
- A "Mark all read" button.
- Per-entry: event type badge, product name (canonical if mapped, `raw_name` otherwise), site name, old → new value display, run timestamp, and a "Mark read" checkbox.

Entries with `seen = 0` are visually distinct (e.g. bold or a coloured left border via `st.markdown` with inline CSS).

### `save_mapping` backfill extended

`db.save_mapping()` already backfills `price_readings.product_id`. It is extended to also update `listings.product_id` for all rows matching the given `raw_name`.

## Testing Decisions

**What makes a good test here:** test the observable state of the database after calling a `db.py` function or running `run_site()`. Do not assert on SQL internals, call counts to internal helpers, or intermediate state. Assert on what a consumer of the function would see: rows in tables, column values, event types emitted.

**Seam 1 — `scraper/db.py`** (primary, in `tests/test_db.py`):

- `upsert_listing` on a new pair sets `first_seen_at = last_seen_at` and `product_url`.
- `upsert_listing` on a known pair updates `last_seen_at` and `latest_price` but does not change `first_seen_at`.
- `upsert_listing` with a null price stores `latest_price = NULL` without raising.
- `write_updates` stores the correct `event_type`, `old_value`, `new_value`, `run_id`.
- `prune_updates` deletes rows older than 30 days and leaves newer rows untouched.
- `get_updates(mapped_only=True)` excludes rows where `product_id IS NULL`.
- `get_updates(mapped_only=False)` includes all rows.
- `mark_updates_seen` sets `seen = 1` for the given ids only.
- `mark_all_updates_seen` sets `seen = 1` for all rows.
- `save_mapping` backfills `listings.product_id` as well as `price_readings.product_id`.

Prior art: `tests/test_db.py` — in-memory SQLite fixture with `schema.sql`, seed site row.

**Seam 2 — `scraper/runner.py`** (secondary, in `tests/test_runner.py`):

- `run_site()` creates a `scrape_runs` row and stamps `run_id` on `price_readings` rows.
- `run_site()` upserts a `listings` row for every product including price-less ones; price-less products do not appear in `price_readings`.
- A product seen for the first time generates a `new_listing` event.
- A product seen again with a different price generates a `price_change` event.
- A product seen again with the same price generates no event.
- A product transitioning from `in_stock=0` to `in_stock=1` on a site with `stock_mode` set generates a `back_in_stock` event; a site without `stock_mode` does not.
- `product_url` is `urljoin`'d against `source_url` for relative hrefs before being stored.

Prior art: `tests/test_runner.py` — in-memory SQLite + `patch("scraper.runner.fetch")` + `patch("scraper.runner.scrape_page")`.

**UI — `app/views/products.py` and `app/views/updates.py`:** no automated tests; validated manually by running the app against the live database.

## Out of Scope

- **Stock detection for sites without `stock_mode`**: backlogged in `backlog.md`. Back-in-stock events are only emitted for the two currently configured sites until this work is done.
- **`product_url` selector coverage audit**: backlogged in `backlog.md`. Several site configs have no selector or a selector that returns no `href`; these silently fall back to the site homepage in the UI.
- **Digest email integration with the updates feed**: the `scraper/digest.py` emailer continues to query `thresholds` directly. Reading from `updates` instead is a future improvement.
- **Price history in the listings panel**: the price-history chart stays on the detail page only.
- **Updates retention configurability**: 30 days is hardcoded. Making it configurable per-operator is not in scope.
- **Per-user read state**: the app has no authentication; `seen` is a single global flag on each row.
- **Automatic stock detection via listing presence/absence** (proxy "disappeared = out of stock"): explicitly ruled out due to false-positive rate from pagination failures and site restructuring.
- **Run-level retry or partial-run resumption**: `scrape_runs.finished_at` being NULL indicates an interrupted run; no recovery logic is added.

## Further Notes

- The `listings` table is the stable identity layer for a (site, raw_name) pair. `price_readings` remains the immutable append-only fact log for prices. These are complementary, not redundant.
- `listings.product_id` is a denormalisation of the `name_mappings` join for query performance in `get_updates` and the listings panel. It must be kept in sync by `save_mapping` and the scraper's upsert path.
- `listings` upserts happen for all scraped products before the `valid = [price is not None]` filter for `price_readings`. This ordering is essential for the no-phantom-new-listing guarantee (Q5 decision).
- The `scrape_runs` row is created in `run_all_sites()`, not in each `run_site()` call, because a "run" is the full batch invocation. All sites scraped in one cron execution share one `run_id`.
- Streamlit 1.50 `st.dataframe` with `selection_mode="single-row"` returns the selected row index in `st.session_state`. The listings panel reads `product_id` from the selected row to query `get_latest_price_per_site`.
