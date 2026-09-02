# 20 — App: Updates, By site, Search

## Question

Rebuild the app around three pages plus the existing Site health. See [spec](../spec-tracker-refocus.md) → "App".

`app/main.py` nav: Updates, By site, Search, Site health.

**Updates** (`app/views/updates.py`, rewritten). Filters: event-type multiselect (default all but `price_rise`), window selectbox (24h / 7d / 30d, default 7d), site selectbox, minimum-drop percent input (default 2, applied to `price_drop` rows only). One `st.dataframe` with a `LinkColumn`: event, name, site, old → new, change %, link, when. No per-row widgets — the current page builds a checkbox per row across 2,856 rows, which is why it is slow. Read state collapses to one "Mark all read" button plus an unread count in the header.

**By site** (`app/views/sites.py`). Top: one row per site — name, listing count, counts by availability, unknown share, `availability_mode` or "not tracked", last scraped, consecutive failures, truncated last error. Sortable, so "which shops have stock tracking working" is one glance. Bottom: a site selectbox, then that site's listings — name, price, availability, link, first seen, last seen — with an availability filter and a name filter.

**Search** (`app/views/search.py`). One text input. Terms split on whitespace, ANDed as case-insensitive `LIKE %term%` over `listings.raw_name`. Results: site, name, price, availability, link, last seen; sortable; capped at 500 rows with a visible note when the cap is hit. A count-by-site summary above the table answers "which shops have this".

**New `scraper/db.py` functions:** `get_site_overview(conn)`, `get_site_listings(conn, site_id, availability=None, term=None)`, `search_listings(conn, terms, limit=500)`, `get_updates(conn, event_types, since, site_id=None, limit=1000)`, `count_unread_updates(conn)`, `mark_all_updates_seen(conn)`. `get_updates`'s `mapped_only` parameter and the `cardmarket_products` join are gone; every query hits the indexes added in ticket 13.

**Tests:** the `db.py` query tests listed in the spec (search term ANDing and case-insensitivity, `get_updates` filters and cap, `get_site_overview` counts and NULL `availability_mode`). Pages themselves are checked by running the app against the rebuilt server DB: both pages should render in well under a second, against ~2,900 listings and a 30-day `updates` window.

**Status: DONE**

The three pages plus Site health render against a 40-site, 2,499-listing, 3,200-update DB in
8 ms to 81 ms. The Updates worst case (30-day window, every event type, no minimum drop, so the
1,000-row cap is what stops it) is 81 ms. `mark_updates_seen` is gone with the per-row checkboxes;
`count_unread_updates` replaces it.

A seventh `db.py` function joined the six the ticket lists: `get_sites`, id and name only. The
Updates page needs the site names for its selectbox, and `get_site_overview` would have grouped
the whole listings table on every render to supply them.

Shared page helpers live in `app/ui.py` (label maps, the connection guard, timestamp trimming,
the link column config), imported as `from app import ui`. It is not under `app/views/`, so it is
not a page: the views folder is the one Streamlit would hijack if it were named `pages/`.

Four things the ticket did not specify:
- The name filter on By site splits on whitespace and ANDs, same as Search, rather than matching
  one substring. Typing two words finding nothing is a worse surprise than the extra terms.
- LIKE terms have `%` and `_` escaped, so a typed `100%` matches the literal string instead of
  the whole catalogue. Case-insensitivity is SQLite's ASCII-only LIKE; matching `É` against `é`
  would need an ICU build.
- Price is a numeric column with a separate currency column, not a formatted `"9.90 EUR"` string.
  The ticket asks for sortable tables, and a formatted string sorts 9.90 above 100.00.
- The count-by-site summary on Search is computed from the returned rows, so when the 500-row cap
  is hit the page says so and says the counts cover only those rows. An exact summary would need
  an uncapped `GROUP BY site_id`, which is a query the ticket does not ask for and which only
  matters for a term broad enough that per-shop counts are not the question.

`get_updates` carries `listings.latest_currency` next to `product_url`, off the same join, so a
price event reads as `299.0 → 249.0 SEK`. One shop prices in SEK, and the write path already
knows it (`price_threshold = 1.0 if SEK`), so a bare number in the feed would be ambiguous.

A `price_drop` row whose stored values will not parse as floats survives the minimum-drop filter.
The filter is there to quiet rounding noise, not to hide events whose size cannot be judged. The
filter runs in Python after the row cap, so the Updates banner says the cap applies to the newest
events and the minimum-drop filter runs on those only. Filtering by magnitude in SQL would mean a
`CAST` on `old_value`, and the ticket fixes `get_updates`'s signature with no minimum-drop
parameter.

Both caps fetch one row past the limit, so "capped" is exact rather than inferred from a full page.

Index use, checked with EXPLAIN QUERY PLAN, is not quite the ticket's "every query hits the
indexes added in ticket 13":
- `get_updates` searches `idx_updates_type_created_at`, then sorts through a temp B-tree, since an
  `IN` over several event types has to merge several ranges. 81 ms on a 3,200-row table.
- `get_site_listings` searches the `(site_id, raw_name)` primary key, which also supplies the name
  ordering; `availability` is a residual test rather than a seek on
  `idx_listings_site_availability`. Right result for a query bounded to one shop's catalogue.
- `search_listings` scans `idx_listings_raw_name`. A `LIKE %term%` cannot seek, so this is the
  cheapest form available.
- `count_unread_updates` scans `updates`. No index covers `seen`, and none was added.

`use_container_width` is deprecated (removal date 2025-12-31, now past) and warned on every
render, so the new pages and `site_health.py` use `width="stretch"`. `site_health.py` also moved
onto `ui.connection()` rather than keeping its own copy of the guard.

Both site selectboxes hold site ids with a `format_func`, not names: two shops could share a name,
and `None` is a cleaner "no filter" than a sentinel string the query has to miss on.

UI verification, per the spec's "no automated tests": `.scratch/tracker-refocus/make_test_db.py`
builds a server-sized DB, `check_pages.py` renders each page through Streamlit's `AppTest` and
times it, `check_interactions.py` drives every widget and re-runs the four pages against an empty
DB. All three live under `.scratch/`, not in `tests/`.

Blocking: nothing
Blocked by: 13, 14, 19
