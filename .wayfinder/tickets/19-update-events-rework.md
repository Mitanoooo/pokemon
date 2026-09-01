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

**Tests** (`tests/test_runner.py`, per the spec's testing decisions): first run silent but listings upserted; second run emits `new_listing`; preorder first sighting emits `new_preorder` only; `in_stock` → `preorder` emits `new_preorder`; both restock transitions emit `back_in_stock` with the old state in `old_value`; lower price → `price_drop`, higher → `price_rise`, equal → nothing; `unknown` on either side of a transition emits nothing; a preorder-URL sighting sets `from_preorder_url` on the listing.

**Status: OPEN**

Blocking: 20
Blocked by: 15
