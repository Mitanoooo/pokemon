# 04 — Investigate and fix 4 permanently-broken sites

**What to build:** Keräilykortti.fi, Porvoon Pelikauppa, Proshop, and Spelparken have never produced a single price reading — all show `consecutive_failures = 2` and `last_error = "NOT NULL constraint failed: price_readings.price"`. With better error reporting from ticket 02 and the paginator fix from ticket 01 in place, do a manual scrape of each site, inspect the actual HTML fetched, and determine the root cause per site. Likely causes include broken selectors returning no products (so `all_readings` is empty and the site is marked failed before any insert), pagination generating bad URLs, or the site blocking the scraper. Fix or update each config until all four sites produce readings, or explicitly mark a site `"disabled": true` with a note if it is structurally unfixable (e.g. JS-rendered, bot-blocked).

**Blocked by:** 01 (paginator fix), 02 (better error reporting).

**Status:** done

- [x] Root cause documented for each of the four sites
- [x] Each fixable site produces at least one price reading after the fix
- [x] Sites that cannot be fixed with requests+BS4 are marked `"disabled": true` with an explanatory `"notes"` entry
- [x] No regression on currently healthy sites

## Root causes

All four sites return **HTTP 200** and parse products fine. None is bot-blocked or
JS-rendered, so none needed `"disabled": true`.

**Shared cause (all four).** `NOT NULL constraint failed: price_readings.price` was
not a per-site fault at all: the pre-fix runner passed every scraped product to
`write_readings`, so one unpriced card aborted the insert and the site lost *all*
its readings for that run and was marked failed. Every one of these shops lists
some unpriced or placeholder-priced item, which is why exactly these four never
got a reading through. `runner._latest_priced_sighting_per_name` (ticket 02) drops
unpriced products before the insert and already fixed the shared cause; this
ticket confirmed it and fixed the one remaining per-site fault.

**Keräilykortti.fi** — no fault. The configured URL is the English-booster
category, and `/page/{page}/` paginates correctly: 12 products on page 1, 1 on
page 2, page 3 empty so the paginator stops. The stale `notes` described the
homepage rather than the configured URL and has been rewritten. **13 readings.**

**Porvoon Pelikauppa** — real fault. The shop lists whole factory cases
("tehdaslaatikko") at 2400–3800 €, all of which `parse_price`'s hardcoded 2000 €
ceiling dropped as suspicious. The bounds check moved into
`price_parser.within_price_bounds`, which honours an optional per-config
`max_price`; this config sets `5000.0`. The lower bound stays at 2 € and still
rejects the shop's 1,00 € pre-order placeholder. **23 readings** (24 cards,
1 placeholder). Both attribute price paths in `_extract_price` now share that
same check — the `itemprop="Price"` branch previously returned its float with no
bounds check at all, so it was the one place a placeholder could still get
through.

**Proshop** — no fault. On the saved page, 4 of 20 cards are legitimately
unpriced: 3 unreleased items render with no `.site-currency-lg` element, and an
internal `*DEMO*` listing carries a 1 340 453,94 € placeholder that the guard
correctly drops. Noted in the config so the gap does not read as a broken
selector. **14 readings** — fewer than the 16 priced cards in the fixture for two
compounding reasons, both expected: the shop lists one product twice
("Portfolio 4-P Pikachu") and `_latest_priced_sighting_per_name` collapses it,
and Proshop's range shifts between fetches, so the live run 10 minutes after the
fixture was saved saw 18 cards rather than 20.

**Spelparken** — no fault. Shopify Dawn markup, selectors and SEK handling all
correct across both pages. **21 readings.**

## Verification

Fresh DB (`init_db.py`) + full live run of all 29 active configs. All four target
sites went from 0 readings to 13 / 23 / 14 / 21, and no previously-productive
site lost readings.

The `max_price` default keeps the delta at zero for every config that does not
set the key, so only Porvoon Pelikauppa's parsing changed. Newly guarding the
`itemprop="Price"` branch does affect the two configs that reach it
(lelupartanen.fi, fantasialinna.com), so their readings were checked against the
bounds first: 2.00–69.95 € and all in range respectively, so the guard drops
nothing there today.

Regression tests in `tests/test_recovered_sites.py` pin each
site's config against a saved page so a future selector edit cannot silently take
one back to zero.

## Out of scope — found during the verification run, logged to `backlog.md`

Two *other* sites produce zero readings. Neither is named in this ticket and
neither is affected by its changes (both lack `max_price`, the only behavioural
delta), so both were left alone:

- **KaruKortti** — 8 products parse, 0 priced. The shop prints dot-decimal
  (`€359.95`) but the config has no `"decimal_separator": "dot"`, so prices parse
  as 35995.00 and the guard drops them. One-line config fix.
- **Swagykarp** — the URL 302s into a CrowdHandler waiting room
  (`wait.crowdhandler.com/...`), returning a 12 KB queue page with no products.
  Candidate for `"disabled": true`.
