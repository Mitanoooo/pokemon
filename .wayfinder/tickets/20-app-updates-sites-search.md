# 20 — App: Updates, By site, Search

## Question

Rebuild the app around three pages plus the existing Site health. See [spec](../spec-tracker-refocus.md) → "App".

`app/main.py` nav: Updates, By site, Search, Site health.

**Updates** (`app/views/updates.py`, rewritten). Filters: event-type multiselect (default all but `price_rise`), window selectbox (24h / 7d / 30d, default 7d), site selectbox, minimum-drop percent input (default 2, applied to `price_drop` rows only). One `st.dataframe` with a `LinkColumn`: event, name, site, old → new, change %, link, when. No per-row widgets — the current page builds a checkbox per row across 2,856 rows, which is why it is slow. Read state collapses to one "Mark all read" button plus an unread count in the header.

**By site** (`app/views/sites.py`). Top: one row per site — name, listing count, counts by availability, unknown share, `availability_mode` or "not tracked", last scraped, consecutive failures, truncated last error. Sortable, so "which shops have stock tracking working" is one glance. Bottom: a site selectbox, then that site's listings — name, price, availability, link, first seen, last seen — with an availability filter and a name filter.

**Search** (`app/views/search.py`). One text input. Terms split on whitespace, ANDed as case-insensitive `LIKE %term%` over `listings.raw_name`. Results: site, name, price, availability, link, last seen; sortable; capped at 500 rows with a visible note when the cap is hit. A count-by-site summary above the table answers "which shops have this".

**New `scraper/db.py` functions:** `get_site_overview(conn)`, `get_site_listings(conn, site_id, availability=None, term=None)`, `search_listings(conn, terms, limit=500)`, `get_updates(conn, event_types, since, site_id=None, limit=1000)`, `count_unread_updates(conn)`, `mark_all_updates_seen(conn)`. `get_updates`'s `mapped_only` parameter and the `cardmarket_products` join are gone; every query hits the indexes added in ticket 13.

**Tests:** the `db.py` query tests listed in the spec (search term ANDing and case-insensitivity, `get_updates` filters and cap, `get_site_overview` counts and NULL `availability_mode`). Pages themselves are checked by running the app against the rebuilt server DB: both pages should render in well under a second, against ~2,900 listings and a 30-day `updates` window.

**Status: OPEN**

Blocking: nothing
Blocked by: 13, 14, 19
