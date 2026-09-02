# Wayfinder Map — Tracker Refocus

## Destination

A four-table tracker (`sites`, `scrape_runs`, `listings`, `updates`) whose only job is to report four things about shop listings: a product seen for the first time, a product opening for preorder, a product going from out of stock to in stock, and a price going down. No canonical product identity, no mapping, no price history, no email. Three pages: Updates, By site, Search.

See [spec](spec-tracker-refocus.md).

## Notes

Stack: Python, SQLite, Streamlit. No Claude API in the loop any more.
Server: Hetzner `65.21.178.63`, DB at `/opt/pokemon/pokemon.db`, app on port 8502.
State at the start of this initiative: 2,738 distinct raw names, 450 of them unmapped or undecided; `price_readings` at 395,722 rows with no indexes; 2,904 listings; 17 of 40 sites with no usable stock detection; zero configs mentioning ennakkotilaus.

**Locked decisions:**
- Mapping is abandoned, not paused. `cardmarket_products`, `name_mappings`, `thresholds`, `price_readings` are dropped; the Updates feed keys on `raw_name` only
- The server DB is rebuilt from a copy, not migrated; the old file is kept as the price-history archive
- `listings.availability` is a four-state string (`in_stock` / `out_of_stock` / `preorder` / `unknown`) plus `availability_text`, the raw badge text, so a misread is re-derivable without re-scraping
- One `availability` config block replaces the six `stock_mode` values; resolution order is text_map, presence, container_class_map, attribute, preorder-URL fallback, default
- A site with no `availability` block reports as "not tracked" rather than as all-unknown; a site with a block must land under 5% unknown
- Price events are split into `price_drop` / `price_rise` at write time; the UI hides rises and applies a minimum-drop percentage
- A site's first run emits no events
- Email is dropped for now. If it comes back it is built on `updates`, not on thresholds
- Updates retention stays 30 days

## Open tickets (frontier → blocked)

None. Every ticket of this initiative is done and deployed. The server ran its first scrape on the new stack at 2026-09-02 10:00 UTC (run 188, 10.8 minutes, 2,946 listings, 27 of 31 sites tracking availability, unknown share 6.2%).

One thing the deploy turned up, unspecified and unfixed: `sites` rows are keyed on `url`, so the config URL fixes of tickets 17 and 18 inserted new site rows and left the old ones behind. Swagykarp and Pelikrypta each have two, the stale one carrying its old failure count (6 and 66) and, for Pelikrypta, one orphan listing. Both show up on By site and Site health as broken shops. Pelikrypta's new URL is a separate problem: it returns 0 products, so its selectors need another look.

## Done

- [13 — Four-table schema and DB rebuild script](tickets/13-four-table-schema-rebuild.md) — `schema.sql` is the four tables plus four indexes; `scripts/rebuild_db.py` builds the new DB from the old one. Run on the server on 2026-09-02: 30 sites, 187 runs, 2,927 listings, 2,958 updates copied, nothing skipped.
- [14 — Strip mapping, products, thresholds and email](tickets/14-strip-mapping-products-thresholds.md) — mapping, catalogue, thresholds, price history and email are gone from the code. Two bridges landed here rather than in 15/19 because 13's schema forced them: `availability` in place of `latest_in_stock`, and `price_drop` / `price_rise` in place of `price_change`. The digest line is out of the server's crontab too (it belongs to the `pokemon` user, not root).
- [15 — Availability config shape and parser](tickets/15-availability-config-and-parser.md) — `detect_availability` returns the four states plus the raw text; 23 configs migrated mechanically, 17 left untracked. Replaying the 10 page fixtures gives zero readings different from the old parser, so nothing is fixed yet and nothing is broken: ticket 18 is where the readings get better.
- [16 — Availability probe CLI](tickets/16-availability-probe-cli.md) — `python -m scraper.probe <config>` dumps a site's badge texts, classes and data attributes with counts, plus the split the current config produces. `--all` prints one coverage line per site, which is how 18 was verified.
- [17 — Preorder URL audit across all 40 sites](tickets/17-preorder-url-audit.md) — 7 of 40 shops have a preorder page whose contents are mostly Pokémon; those went into `preorder_urls`. The audit also moved the `from_preorder_url` check ahead of the badge forms, since every added URL badges its items as plain in-stock or sold-out.
- [18 — Availability pin-down pass across all 40 sites](tickets/18-availability-pin-down-pass.md) — 27 of the 29 enabled configs now carry an availability block checked against live HTML; kevinshobbyshop (HTTP 403) and karkkainen (no signal on the listing) are the exceptions.
- [19 — Update events rework](tickets/19-update-events-rework.md) — `_build_update_events` writes the four signals; a first run is silent; no transition fires from or to `unknown`, so untracked sites need no guard of their own. A fetch failure mid-pagination no longer discards the events of the pages that did land.
- [20 — App: Updates, By site, Search](tickets/20-app-updates-sites-search.md) — three pages of `st.dataframe`, no per-row widgets, under 85 ms each against server-sized data. Read state is one "Mark all read" button and an unread count. Seven new `db.py` query functions; shared page helpers in `app/ui.py`. Live since 2026-09-02; against the server's own data the four pages render in 21 to 184 ms.

## Decisions so far

- A `price_change` row whose old and new values are equal is skipped by the rebuild along with the unparseable ones, since there is no direction to record.
- `unknown` → `preorder` emits nothing, like every other transition touching `unknown`. It drops a real preorder signal on the four sites whose availability block defaults to `unknown`; revisit once there is real data on how often a badge goes unreadable and back.
- A `back_in_stock` row carries the previous availability in `old_value`; every other event type puts the price in `new_value` and leaves `old_value` either empty or the old price.
- Name search is SQLite `LIKE` with `%` and `_` escaped: case-insensitive for ASCII only. Matching `É` against `é` would need an ICU build, and no listing name has needed it yet.

Two earlier initiatives are closed and superseded:
- **Normalisation overhaul** (tickets 01–05) and **accuracy overhaul** (tickets 06–12) built the mapping pipeline that ticket 14 now deletes. Their specs stay in `.wayfinder/` as history: [accuracy overhaul](spec-accuracy-overhaul.md), [interface improvements](spec-interface-improvements.md). The ticket files were removed from the working tree; they are in git history at `90ce2e5`.

## Not yet specified

- Whether shops with no separate preorder page can have preorders detected from badges alone (ticket 17 records the cases, ticket 18 decides per site)
- What to do about a shop renaming a product, which currently reads as a new listing
- Whether `updates` needs a longer window than 30 days once the feed is the only view

## Out of scope

- Canonical product identity and anything that needs it
- Price history, charts, thresholds, alerts
- Email digest (removable now, rebuildable later on `updates`)
- Preorder release-date parsing out of badge text
- Treating a disappearing listing as out of stock (ruled out previously for false positives)
- Per-user read state
