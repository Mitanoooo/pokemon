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

- [15 — Availability config shape and parser](tickets/15-availability-config-and-parser.md) *(frontier)*
- [16 — Availability probe CLI](tickets/16-availability-probe-cli.md) — blocked by 15
- [17 — Preorder URL audit across all 40 sites](tickets/17-preorder-url-audit.md) — blocked by 15
- [18 — Availability pin-down pass across all 40 sites](tickets/18-availability-pin-down-pass.md) — blocked by 16
- [19 — Update events rework](tickets/19-update-events-rework.md) — blocked by 15
- [20 — App: Updates, By site, Search](tickets/20-app-updates-sites-search.md) — blocked by 19

Tickets 17 and 18 are the ones that make preorder and restock detection real; the rest is scaffolding around them. Both are per-site audit passes and cannot be fully automated.

## Done

- [13 — Four-table schema and DB rebuild script](tickets/13-four-table-schema-rebuild.md) — `schema.sql` is the four tables plus four indexes; `scripts/rebuild_db.py` builds the new DB from the old one. Not deployed yet: it ships with 14.
- [14 — Strip mapping, products, thresholds and email](tickets/14-strip-mapping-products-thresholds.md) — mapping, catalogue, thresholds, price history and email are gone from the code. Two bridges landed here rather than in 15/19 because 13's schema forced them: `availability` in place of `latest_in_stock`, and `price_drop` / `price_rise` in place of `price_change`. The digest line is out of the server's crontab too (it belongs to the `pokemon` user, not root).

## Decisions so far

- A `price_change` row whose old and new values are equal is skipped by the rebuild along with the unparseable ones, since there is no direction to record.

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
