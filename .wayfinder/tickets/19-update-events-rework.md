# 19 — Update events: preorder, restock, price direction, first-run guard

## Question

Rework `_build_update_events` in `scraper/runner.py` for the four signals the operator actually wants. See [spec](../spec-tracker-refocus.md) → "Event rules".

**Rules, diffing this run's sightings against the pre-upsert `listings` state:**

- **First-run guard.** `get_listing_state()` empty for this site → upsert listings, emit nothing. Adding a shop must not bury the feed under its whole catalogue (most of the 2,668 historical `new_listing` rows are exactly that).
- **`new_listing`** — first sighting, availability is not `preorder`. `new_value` = price.
- **`new_preorder`** — first sighting with availability `preorder`, or a transition into `preorder` from any other state. `new_value` = price. Never emitted alongside `new_listing` for the same sighting.
- **`back_in_stock`** — `out_of_stock` → `in_stock`, or `preorder` → `in_stock`. `old_value` = the previous availability string, so release-day restocks are distinguishable.
- **`price_drop` / `price_rise`** — both prices known and differing by at least 0.01 EUR (1.0 SEK), as today, but written as two event types instead of one `price_change`. No magnitude filter at write time; ticket 20's UI slider does the quieting.
- `product_id` is gone from the event dict and from `write_updates`.
- The old `stock_mode`-not-unknown guard is gone. Availability is now `unknown` for untracked sites, and no transition rule fires from or to `unknown`, which achieves the same thing without special-casing.

Retention stays at 30 days via `prune_updates`.

**Also fix here: a mid-run fetch failure drops that run's events for good.**
`_scrape_source_url` commits its listings per page, but `_build_update_events` runs after
every source URL, inside the same `try`. A 500 on the last page therefore keeps the already
committed listings and writes no events, and the next run diffs against those updated rows,
so the price drop or restock in between is never reported. Build and write the events for the
source URLs that did succeed, or roll the listing writes back with them. Test: a two-URL site
whose second URL raises still emits the first URL's events.

**Tests** (`tests/test_runner.py`, per the spec's testing decisions): first run silent but listings upserted; second run emits `new_listing`; preorder first sighting emits `new_preorder` only; `in_stock` → `preorder` emits `new_preorder`; both restock transitions emit `back_in_stock` with the old state in `old_value`; lower price → `price_drop`, higher → `price_rise`, equal → nothing; `unknown` on either side of a transition emits nothing; a preorder-URL sighting sets `from_preorder_url` on the listing.

**Status: DONE**

`_build_update_events` no longer takes `availability_mode`: excluding `unknown` from both sides
of a transition covers the untracked sites on its own. The transitions live in one
`(previous, new) -> event_type` table. `product_id` was already gone from the event dict and
`write_updates`, having landed with ticket 14.

The two rules above conflict on one pair, and this ticket's own text does too: "a transition
into `preorder` from any other state" would include `unknown` → `preorder`, while "no transition
rule fires from or to `unknown`" excludes it. Implemented as excluded. It costs nothing on an
untracked site (always `unknown`, so no transition is ever visible there) but it does drop a
real signal on the four sites whose block sets `"default": "unknown"`: a listing whose badge was
unreadable last run and says Ennakkotilaus this run produces no event. Worth revisiting once
there is a run's worth of real availability data to judge the false-positive rate on.

The mid-run failure fix is page-level, not source-URL-level: `_scrape_source_url` appends into a
list the caller owns, so the pages that landed before a 500 survive the raise, and `run_site`
writes their events from a `finally` before the failure propagates to the health handler. A
source-URL-level fix would have left the common case (one URL, several pages) broken.

Blocking: 20
Blocked by: 15
