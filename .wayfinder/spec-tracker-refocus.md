# Spec — Tracker Refocus (Drop Mapping, Availability-First Updates)

## Problem Statement

The tracker was built around a canonical product catalogue: every scraped `raw_name` had to be mapped to a Cardmarket `idProduct` before it could appear anywhere useful. That machinery now costs more than it returns. 450 of 2,738 distinct raw names are still unmapped or undecided, the Updates feed hides events for all of them by default, and the products page joins a 395,722-row `price_readings` table that has no indexes at all, so it takes tens of seconds to render. Most of what it renders is dead stock: products sitting on shop pages that will never be available again.

The operator does not want a canonical price database. They want four signals: a product appearing for the first time, a product appearing as a preorder (ennakkotilaus), a product going from out of stock to in stock, and a price going down. All four are properties of a shop listing, not of a canonical product, so none of them need mapping.

Two of those four signals do not work today. Preorder is not represented anywhere: `detect_stock` returns only true/false/none, no site config names a preorder category URL, and no config recognises an "Ennakkotilaus" badge, so preorders are currently reported as ordinary stock or ordinary absence. Back-in-stock only fires for sites with a usable `stock_mode`, and 17 of 40 configs have none (11 omit the key, 6 set `"unknown"`), leaving 327 listings with no stock state at all.

## Solution

Strip the tracker down to shop listings and events over them, then spend the freed effort on scrape coverage and availability accuracy.

1. **Four tables.** `sites`, `scrape_runs`, `listings`, `updates`. `cardmarket_products`, `name_mappings`, `thresholds` and `price_readings` are dropped. The server DB is rebuilt from a copy rather than migrated in place; the old file stays on disk as the price-history archive.

2. **Availability replaces in-stock.** `listings.availability` is one of `in_stock`, `out_of_stock`, `preorder`, `unknown`, with the raw badge text kept alongside it so a misread can be re-derived without re-scraping. Site configs get one general `availability` block in place of the six ad-hoc `stock_mode` values.

3. **Four event types.** `new_listing`, `new_preorder`, `back_in_stock`, `price_drop` (plus `price_rise`, written but hidden by default). Events carry `raw_name` only; no product id.

4. **Preorder URLs.** Each site config gains a `preorder_urls` list, audited site by site. Sightings from those URLs are flagged, which backs up badge detection where a shop has no preorder badge.

5. **Three pages.** Updates (the point of the app), By site (browse one shop's listings, and see which shops have working stock tracking), Search (find a term across all shops). No product page, no mapping review, no thresholds, no price history, no email.

## User Stories

1. As the operator, I want the Updates page to load in under a second, so that checking it is a habit rather than a chore.
2. As the operator, I want an event when a shop lists a product I have never seen there, so that I hear about new releases as they land.
3. As the operator, I want a separate event when a listing is a preorder, so that ennakkotilaus openings stand out from ordinary restocks.
4. As the operator, I want the preorder event to carry the price, so that I can judge it without opening the shop.
5. As the operator, I want an event when a listing goes from out of stock to in stock, and when a preorder goes to in stock, so that I can act on release day.
6. As the operator, I want price events limited to drops by default, with a minimum size I can adjust, so that rounding noise does not fill the feed.
7. As the operator, I want to filter updates by event type, time window and site, so that I can answer "what is new this week" and "what dropped today" from the same page.
8. As the operator, I want every update row to link straight to the shop's product page, so that acting on an event is one click.
9. As the operator, I want no mapping step anywhere in the update path, so that a new product produces an event the first run it is seen.
10. As the operator, I want to pick a shop and browse everything the scraper sees there, with price and availability, so that I can sanity-check a shop's coverage by eye.
11. As the operator, I want a per-shop view of how well stock tracking works there, so that I know whether that shop's silence means "nothing changed" or "we cannot tell".
12. As the operator, I want shops with no stock tracking configured to say so explicitly rather than showing everything as unknown, so that I can tell a gap from a failure.
13. As the operator, I want to type a search term and see which shops have a matching listing, with price and availability, so that I can price-check without a canonical catalogue.
14. As the operator, I want preorder category URLs scraped for every shop that has one, so that preorders are seen at all.
15. As the operator, I want each site's availability badges pinned down against real HTML, so that fewer than 5% of its listings resolve to unknown, or the site is honestly marked as untracked.
16. As the operator, I want a probe command that dumps a site's badge texts and classes with counts, so that pinning a site down takes minutes, not an afternoon.
17. As the operator, I want a brand-new site's first run to produce no events, so that adding a shop does not bury the feed under its whole catalogue.
18. As the operator, I want the old price history preserved as a file rather than deleted, so that dropping the table is reversible in principle.

## Implementation Decisions

### Schema (the whole DB)

`sites` keeps its existing columns and gains one:

```
availability_mode  TEXT   -- resolution forms configured for this site, comma-joined
                          -- in precedence order (e.g. "text_map,container_class");
                          -- NULL means the config has no availability block
```

Written on every run from the site's config, so the app never reads config files.

`scrape_runs` unchanged.

`listings` loses `product_id` and `latest_in_stock`, gains availability:

```
site_id            INTEGER NOT NULL REFERENCES sites(id)
raw_name           TEXT NOT NULL
PRIMARY KEY (site_id, raw_name)
product_url        TEXT
first_seen_at      TEXT NOT NULL
last_seen_at       TEXT NOT NULL
last_run_id        INTEGER REFERENCES scrape_runs(id)
latest_price       REAL
latest_currency    TEXT
availability       TEXT NOT NULL DEFAULT 'unknown'
                   CHECK (availability IN ('in_stock','out_of_stock','preorder','unknown'))
availability_text  TEXT     -- raw badge text or class list that produced it, capped 120 chars
from_preorder_url  INTEGER NOT NULL DEFAULT 0 CHECK (from_preorder_url IN (0,1))
```

`availability` is overwritten on every sighting: it means "state as of the last time we saw this listing", not "best state ever known". `latest_price` keeps its COALESCE behaviour (a sighting with no parseable price does not erase the last known price). Losing a badge cannot manufacture a false restock, because restock fires only on an explicit `out_of_stock`/`preorder` → `in_stock` transition.

`updates` loses `product_id` and splits price events by direction:

```
id          INTEGER PRIMARY KEY AUTOINCREMENT
run_id      INTEGER REFERENCES scrape_runs(id)
site_id     INTEGER NOT NULL REFERENCES sites(id)
raw_name    TEXT NOT NULL
event_type  TEXT NOT NULL CHECK (event_type IN
              ('new_listing','new_preorder','back_in_stock','price_drop','price_rise'))
old_value   TEXT
new_value   TEXT
created_at  TEXT NOT NULL DEFAULT (datetime('now'))
seen        INTEGER NOT NULL DEFAULT 0
```

Indexes (the current DB has none outside primary keys):

```
listings(raw_name)
listings(site_id, availability)
updates(created_at DESC)
updates(event_type, created_at DESC)
```

Direction is decided at write time rather than by `CAST` in the UI query, so the event-type index does the filtering.

### Rebuild, not migrate

`scripts/rebuild_db.py --source pokemon.db --target pokemon.db.new` creates the target from the new `schema.sql` and copies:

- `sites` verbatim (`availability_mode` left NULL until the next scrape run fills it)
- `scrape_runs` verbatim
- `listings` minus `product_id`, translating `latest_in_stock`: `1` → `in_stock`, `0` → `out_of_stock`, `NULL` → `unknown`; `availability_text` NULL, `from_preorder_url` 0
- `updates` minus `product_id`, translating `price_change` into `price_drop` or `price_rise` by comparing `old_value` and `new_value` as floats (a row where either side will not parse is skipped and counted)

It prints per-table source and target counts, and refuses to overwrite an existing target without `--force`. Server swap: run mid-hour (cron scrapes at :00), verify counts, `mv pokemon.db pokemon.db.pre-refocus-<date>`, `mv pokemon.db.new pokemon.db`, `systemctl restart pokemon-streamlit` (the app caches its connection via `st.cache_resource`, so a restart is required). The archived file is where the 395k price readings live from then on.

### Availability config shape

One `availability` block replaces `stock_mode`, `stock_badge_text` and the `in_stock` selector:

```json
"availability": {
  "selector": "span.stock-badge",
  "text_map": {"Varastossa": "in_stock", "Loppu": "out_of_stock",
               "Ennakkotilaus": "preorder"},
  "presence": {"selector": "button.add-to-cart",
               "present": "in_stock", "absent": "out_of_stock"},
  "container_class_map": {"instock": "in_stock", "outofstock": "out_of_stock",
                          "unavailable": "out_of_stock"},
  "attribute": {"name": "data-ls-availability",
                "map": {"InStock": "in_stock", "OutOfStock": "out_of_stock",
                        "PreOrder": "preorder"}},
  "default": "unknown"
}
```

Every key is optional. `detect_availability(container_el, config, from_preorder_url)` resolves in this fixed order and returns the first hit as `(availability, availability_text)`:

0. `from_preorder_url` is 1 → `preorder`, `availability_text` = `"(preorder url)"`, whatever the badge says. Ticket 17 moved this ahead of the forms: a block carrying both `present` and `absent` always resolves, so ranked last the flag was dead for the 14 `presence` sites, and the audit found that every added preorder URL badges its items as plain in-stock or sold-out. A site with no `availability` block at all still reads `unknown`; only `listings.from_preorder_url` records the provenance there.
1. `text_map` against the text of every element matching `selector`. Text is casefolded and whitespace-collapsed; keys are matched as substrings, longest key first, so `"Ennakkotilaus 12.9.2026"` still resolves. `availability_text` is the matched element's raw text.
2. `presence` on its own selector.
3. `container_class_map` against the container's own class list. `availability_text` is the class list joined by spaces.
4. `attribute` on the element matching `selector` (or the container if no selector).
5. `default`, normally `unknown`.

Migration of the 23 configs that have a usable `stock_mode`: `normal`/`inverted` become `presence`, `badge_text` becomes a `text_map` with the old badge text mapped to `out_of_stock` and `"default": "in_stock"`, `container_class` becomes `container_class_map`, `attribute` becomes `attribute`. Configs with `"unknown"` or no key get no `availability` block, which is what makes the app report them as untracked instead of silently unknown. `stock_mode` is deleted from every config and from the parser; `tests/test_site_configs.py` gains a check that no config still names it.

### Preorder URLs

`preorder_urls` is a new config array alongside `source_url` / `source_urls`. `paginator.tagged_source_urls()` returns the normal URLs and then the preorder ones, each paired with its flag, while `source_urls()` stays normal-only because its first entry is the site identity; `runner._scrape_source_url` passes `from_preorder_url` into the parser and the listings upsert. A listing seen on both a normal and a preorder URL in the same run keeps the last sighting's flag, which matches how duplicate sightings are already deduped (last occurrence wins).

Audit deliverable: `.scratch/tracker-refocus/preorder-urls.md`, one line per site recording the URL found or "none exists", in the shape of the ticket-06 multi-URL audit. Result: 7 of 40 shops have a usable one (korttistoppi, pbcards, peliparatiisi, pokepulls, spelparken, swagykarp, tcgkauppa). Only URLs whose contents are mostly Pokémon go into a config, because nothing filters listings by name and a shop-wide preorder page would import Warhammer and electronics too.

### Probe tool

`python -m scraper.probe <config.json>` fetches page 1 of each of a site's URLs (or `--html-file` for a saved fixture) and prints, per product container:

- distinct container class lists with counts
- distinct text of the configured `selector` plus heuristic candidates (`[class*=stock]`, `[class*=avail]`, `[class*=badge]`, `[class*=saatav]`, `[class*=ennakko]`)
- distinct `data-*` attribute values whose name contains `avail` or `stock`
- the availability split the current config produces, with the unknown share

`--all` loops every config and prints one coverage line per site, which is how ticket 18 is verified.

### App

`main.py` nav becomes: Updates, By site, Search, Site health.

**Updates** (`app/views/updates.py`, rewritten). Filters: event type multiselect (default all but `price_rise`), window selectbox (24h / 7d / 30d, default 7d), site selectbox, minimum drop input in percent (default 2, applied to `price_drop` rows only). Rendered as one `st.dataframe` with a `LinkColumn`, not a per-row widget loop: the current page builds a checkbox per row for 2,856 rows, which is the actual reason it is slow. Columns: event, name, site, old → new, change %, link, when. Read state collapses to a single "Mark all read" button plus an unread count in the header.

**By site** (`app/views/sites.py`). Top half: one row per site with listing count, counts by availability, unknown share, `availability_mode` (or "not tracked"), last scraped, consecutive failures, truncated last error. Bottom half: a site selectbox, then that site's listings as name, price, availability, link, first seen, last seen, with an availability filter and a name filter.

**Search** (`app/views/search.py`). One text input. Terms split on whitespace and ANDed as case-insensitive `LIKE %term%` over `listings.raw_name`. Results: site, name, price, availability, link, last seen, sortable, capped at 500 rows with a note when the cap is hit. A count-by-site summary sits above the table.

`scraper/db.py` after the strip: `get_connection`, `start_run`, `finish_run`, `get_listing_state`, `upsert_listing`, `write_readings` (deleted), `write_updates`, `prune_updates`, `update_site_health`, plus new `get_site_overview`, `get_site_listings`, `search_listings`, `get_updates`, `count_unread_updates`, `mark_all_updates_seen`.

### Event rules

- **First run guard.** If `get_listing_state()` returns nothing for a site, upsert the listings and skip event generation for that site entirely.
- **`new_listing`** on a first sighting whose availability is not `preorder`.
- **`new_preorder`** on a first sighting whose availability is `preorder`, and on any transition into `preorder` from another state. `new_value` is the price.
- **`back_in_stock`** on `out_of_stock` → `in_stock` and on `preorder` → `in_stock`. `old_value` is the previous availability, so release-day restocks are distinguishable from ordinary ones.
- **`price_drop` / `price_rise`** when both prices are known and differ by at least 0.01 EUR (1.0 SEK), as today. No magnitude filter at write time; the UI slider does the quieting.
- Retention stays 30 days via `prune_updates`.

## Testing Decisions

**What makes a good test here:** assert on database state after a `db.py` call or a `run_site()` call, and on the `(availability, availability_text)` tuple returned by the parser. Do not assert on SQL text, selector internals, or helper call counts.

**`tests/test_parser.py`** (replacing the 15 `detect_stock` tests): one test per resolution form, plus precedence tests (`text_map` beats `container_class_map`; `from_preorder_url` beats every form, including a badge that says otherwise), substring matching with a trailing date, casefolding, missing block → `unknown`, and `availability_text` content per form. Existing fixture-driven `scrape_page` tests for tcgkauppa, peliparatiisi and karkkainen are updated to the new return shape.

**`tests/test_runner.py`**: first run emits no events but does upsert listings; second run emits `new_listing`; a preorder first sighting emits `new_preorder` and not `new_listing`; `in_stock` → `preorder` emits `new_preorder`; `preorder` → `in_stock` and `out_of_stock` → `in_stock` both emit `back_in_stock` with the old state in `old_value`; a lower price emits `price_drop`, a higher one `price_rise`, an equal one nothing; a sighting from a preorder URL sets `from_preorder_url`.

**`tests/test_db.py`** (trimmed): `upsert_listing` overwrites `availability` but not a known `latest_price` when the new price is NULL; `search_listings` ANDs terms and is case-insensitive; `get_updates` honours event type, window and site filters and the row cap; `get_site_overview` counts by availability and reports `availability_mode` NULL as untracked; `prune_updates` unchanged.

**`tests/test_rebuild_db.py`** (new): build an old-schema in-memory DB, run the copy, assert row counts, the `latest_in_stock` → availability translation, the `price_change` split by direction, and that an unparseable price row is skipped and counted.

**Deleted test files:** `test_apply_batch.py`, `test_calibration_candidates.py`, `test_calibration_examples.py`, `test_extract_catalog.py`, `test_digest.py`, `test_setup_email.py`, `test_writeback_db.py`, `test_app_db.py`.

**UI:** no automated tests. Validated by running the app against the rebuilt server DB.

## Out of Scope

- **Canonical product identity.** No mapping, no Cardmarket catalogue, no canonical names anywhere. Raw listing names only.
- **Price history and charts.** The archived DB file keeps the old readings; nothing in the app reads them.
- **Email digest.** `scraper/digest.py`, `scripts/setup_email.py` and the digest cron line are removed. Re-adding it later means building it on `updates`, not on thresholds.
- **Thresholds and price alerts.** Gone with the table.
- **Renamed-listing false positives.** A shop editing a product title creates a new `(site_id, raw_name)` pair and reads as a new product. Accepted for now; fuzzy same-site matching is a later idea.
- **Preorder release dates.** The badge text is stored raw; parsing a date out of it is not attempted.
- **Per-user read state.** The app has no auth; `seen` stays a single global flag.
- **Listing-gone events.** Still not emitted; `last_seen_at` drifts instead.
- **Automatic stock detection from listing disappearance.** Ruled out previously for false positives; the ruling stands.

## Further Notes

- Dropping `price_readings` removes the only table that grows without bound, so the retention job the earlier plan needed is no longer necessary. `updates` is capped at 30 days and `listings` is bounded by shop catalogue size (2,904 rows today).
- `availability_text` exists so that an availability pass can be redone from stored data. Any per-site badge fix should be checked against it before re-scraping.
- The 17 untracked sites are the reason `back_in_stock` looks rare (54 events ever). Tickets 16 and 18 are the ones that make the second signal real; everything else is scaffolding around it.
- No config mentions ennakkotilaus today, so ticket 17 is not a coverage improvement to an existing signal, it is the whole signal.
