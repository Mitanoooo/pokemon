# 03 — Update event generation and Updates page

**What to build:** The scraper diffs each site's new listings state against the previous state and writes events to the `updates` table. A new Updates page in the app surfaces this feed so the operator can see at a glance what changed since the last run, filter by mapped products, and mark entries as read.

**Scraper side:**

For each site, before upserting new listings, the runner captures the previous state via `get_listing_state`. After the upsert it diffs old vs new and emits events:

- `new_listing` — the `(site_id, raw_name)` pair did not exist before this run.
- `price_change` — the listing existed before, both the old `latest_price` and the new price are non-null, and they differ by ≥ €0.01 (or ≥ 1 for SEK).
- `back_in_stock` — the listing existed before with `latest_in_stock = 0`, the new `in_stock = 1`, and the site config has a `stock_mode` other than `None`/`'unknown'`. (Most sites have no `stock_mode`; this event is silently skipped for them.)

At the end of `run_all_sites()`, rows in `updates` older than 30 days are pruned.

New `scraper/db.py` functions: `write_updates`, `prune_updates`, `get_updates` (returns rows newest-first, optionally filtered to `product_id IS NOT NULL`), `mark_updates_seen`, `mark_all_updates_seen`.

**App side:**

A new `app/views/updates.py` page accessible from the sidebar as "Updates". It shows:

- A toggle labelled "Show unmapped" (default off) that switches `get_updates(mapped_only=...)`.
- A "Mark all read" button.
- One entry per event: event-type badge (`price_change` / `new_listing` / `back_in_stock`), product name (canonical name if `product_id` is set, `raw_name` otherwise), site name, old → new value, run timestamp, and a checkbox to mark that entry read.
- Unread entries are visually distinct from read ones.

`app/main.py` sidebar navigation gains an "Updates" entry pointing at the new page.

**Blocked by:** 02 — Scraper: run tracking and listings persistence.

**Status:** ready-for-agent

- [ ] Running the scraper twice produces `price_change` events for listings whose price shifted between runs.
- [ ] A `(site_id, raw_name)` pair seen for the first time produces exactly one `new_listing` event.
- [ ] A `(site_id, raw_name)` pair seen again with the same price produces no event.
- [ ] A listing transitioning from `in_stock=0` to `in_stock=1` on a site with `stock_mode` configured produces a `back_in_stock` event; the same transition on a site without `stock_mode` produces no event.
- [ ] `prune_updates` deletes rows with `created_at` older than 30 days and leaves newer rows untouched.
- [ ] `get_updates(mapped_only=True)` returns only rows where `product_id IS NOT NULL`.
- [ ] `get_updates(mapped_only=False)` returns all rows.
- [ ] `mark_updates_seen([id1, id2])` sets `seen=1` for exactly those ids.
- [ ] `mark_all_updates_seen()` sets `seen=1` for all rows.
- [ ] The Updates page renders in the app, shows the feed, and the "Mark all read" and per-row checkboxes update `seen` state correctly on rerun.
- [ ] `tests/test_db.py` covers all new db functions per the acceptance criteria above.
- [ ] `tests/test_runner.py` covers: `price_change` event emitted on price delta; no event when price unchanged; `new_listing` event for first-seen pair; `back_in_stock` only when `stock_mode` is set.
- [ ] `python -m pytest tests/` passes.
