# 17 — Preorder URL audit across all 40 sites

## Question

No site config mentions ennakkotilaus, preorder or tulossa today, so preorder listings are either never fetched or fetched from a normal category with a badge nobody parses. Add the URLs and the provenance plumbing. See [spec](../spec-tracker-refocus.md) → "Preorder URLs".

**Config:** new `preorder_urls` array alongside `source_url` / `source_urls`.

**Plumbing:**
- `paginator.source_urls(config)` returns preorder URLs too, tagged so the caller knows which is which (e.g. a list of `(url, is_preorder)` pairs, with the existing string-list helper kept for the site-identity lookup, which must stay the first normal URL).
- `runner._scrape_source_url` passes `from_preorder_url` into `detect_availability` and into `upsert_listing`.
- A listing seen on both a normal and a preorder URL in one run keeps the last sighting's flag, matching the existing "last occurrence wins" dedupe.

**Decide first: where does the flag sit in the resolution order?** Ticket 15 put
`from_preorder_url` last, after every form, which makes it dead for the 14 `presence`
sites: a block with both `present` and `absent` always returns a state, so the flag can
never be reached. Left alone, wiring `preorder_urls` would only change readings on the
`text_map` and untracked sites. Either the flag outranks the forms for pages fetched from a
preorder URL, or it at least outranks the `absent` branch. Pick one here and change
`detect_availability` with it; the parser tests for precedence live in `tests/test_parser.py`.

**Audit, per site (40):** find the shop's preorder category or tag URL. Candidate patterns to check: `/ennakkotilaus`, `/ennakkotilaukset`, `/ennakko`, `/tulossa`, `/pre-order`, `/preorder`, `/kommande`, `/kommer-snart`, plus the shop's own tag and filter URLs. Verify the page actually lists products and paginates the same way the site's other URLs do. Where a shop has no separate preorder page, record that and note whether its normal categories carry preorder items with a badge (that case is ticket 18's problem, not this one).

The same pass re-checks normal category coverage: a product that is never fetched can never produce an event. Where a gap is obvious, add the URL.

**Deliverable:** `.scratch/tracker-refocus/preorder-urls.md`, one line per site: site, preorder URL or "none exists", product count seen on it, notes. Same shape as the ticket-06 multi-URL audit.

**Tests:** `tests/test_site_configs.py` checks that every `preorder_urls` entry is an absolute URL on the site's own host. `tests/test_runner.py` covers the `from_preorder_url` flag reaching `listings` (that test belongs to ticket 19's set; either ticket may land it).

**Status: DONE**

Decision on the resolution order: the flag outranks every form. Ranked after them it stayed
dead for the 14 `presence` sites, and on the six added preorder pages that had products to
read (pbcards' was empty), the badges say plain in-stock (korttistoppi 12/12, spelparken 8/8)
or sold-out (pokepulls 10/10, peliparatiisi 6/6, swagykarp 6 of 8, tcgkauppa 22 of 27) —
never preorder — so any lower rank would have read them wrong. A site with no `availability` block still reads `unknown`; `listings.from_preorder_url`
records the provenance regardless.

Audit result (`.scratch/tracker-refocus/preorder-urls.md`): 7 of 40 shops have a usable
preorder URL, now in their configs — korttistoppi, pbcards, peliparatiisi, pokepulls,
spelparken, swagykarp, tcgkauppa. 8 more have a preorder page that was left out (mostly
Warhammer or electronics, or empty), 1 (kevinshobbyshop) has a preorder filter URL that stops
filtering on page 2, 22 have none, 2 are unreachable (403). 7 + 8 + 1 + 22 + 2 = 40. Normal-coverage
fixes from the same pass: pelikrypta's `source_url` 404ed and was replaced, and pbcards'
absolute `pagination.url_pattern` became query-only so a second URL cannot paginate into the
first.

Blocking: nothing
Blocked by: 15
