# Preorder URL audit

**Date:** 2026-09-02
**Ticket:** 17
**Method:** four automated passes over all 40 site configs, every candidate URL fetched
and parsed with the site's own selectors (`.scratch/tracker-refocus/find_preorder_urls.py`,
`find_preorder_urls2.py`, `pass3.py`, `pass4.py`, `pass5.py`):

1. crawl the front page links and the sitemaps for preorder wordings
   (`ennakkotilaus`, `ennakko`, `tulossa`, `pre-order`, `förköp`, `kommande`, …)
2. ask the shop software for its category list: Shopify `/collections.json`,
   WooCommerce `product_cat` sitemaps and the Store API, plus per-platform guesses
3. hand-picked follow-ups: tag URLs, filter parameters, locale variants, page 2
4. controls: `products.json` counts to tell an empty collection from a selector
   miss, a nonsense path to tell a real category from a soft-404 listing, and the
   same page with and without a filter parameter to see whether it filters at all

Counts are products parsed on page 1 at audit time.

---

## One line per site

| Site | Preorder URL | Products | Notes |
|---|---|---|---|
| **Blockhousegames** | `/collections/ennakkotilaukset` | 24 (67 total) | exists, not used: 1 of 24 is Pokémon, the rest Warhammer. `/ennakkotilaukset/pokemon` and `?filter.p.product_type=Pokémon` return the collection unfiltered |
| **Casagrande** | none exists | – | `/collections/ennakkotilaukset` and `/collections/pre-order` 404; no preorder collection in `collections.json` |
| **CDON** (disabled) | none found | – | JS-rendered; nothing preorder-shaped in the sitemaps |
| **Ellimadelli** | `/collections/ennakkotilaus-tuotteet` | 0 | exists, not used: shop-wide toy preorders (Littlest Pet Shop etc.), empty at audit time (`products.json` = 0) |
| **Euro Elite Cards** (disabled) | `/ennakkotilaus` | 0 | page loads but lists nothing our selectors see; sports-card shop, site dropped by operator decision |
| **Fantasialinna** | none exists | – | `/verkkokauppa/ennakkotilaukset` and `/verkkokauppa/ennakot` 404 |
| **Flea** | none exists | – | no preorder collection; only an availability filter (`?filter.v.availability=0`, 9 out-of-stock items) |
| **GodOfCards** | `/en-fi/collections/pre-order` | 0 | exists, not used: empty at audit time (`products.json` = 0) and shop-wide (MTG, Yu-Gi-Oh, Pokémon), `?filter.p.product_type=Pokemon` gives nothing either |
| **Hobbyhall** (disabled) | not auditable | – | HTTP 403 on every fetch |
| **Kärkkäinen** | none exists | – | `/verkkokauppa/ennakkotilaukset` 404. `?availability=PreOrder` is ignored: 57 products with and without it, same first items |
| **KaruKortti** | none exists | – | `/kategoria/ennakkotilaukset`, `/category/ennakkotilaukset`, `/kategoria/ennakko` all 404 |
| **Keräilykortti.fi** | none exists | – | `/ennakkotilaukset/`, `/ennakkotilaus/`, `/ennakko/`, `/tulossa/` all 404 (site also timed out twice before answering) |
| **KevinsHobbyShop** | filter URL, not usable | 15 | `?filter_availability=pre-order` returns 15 Pokémon items on page 1 but the filter is dropped on page 2 (Dragon Shield sleeves), so the first page is not a preorder listing either |
| **Kodintavaratalo** | none exists | – | `/ennakkotilaukset` and `/tulossa` 404 |
| **Konsolinet** (disabled) | `/category/101/ennakkotuotteet` | 0 | console-game preorders, no Pokémon; site is behind a bot check anyway |
| **Korttistoppi** | **`/tuoteryhma/ennakkotilaus`** ✅ | 12 | added. Note the singular slug (`ennakkotilaus`, not `-tilaukset`). All 12 Pokémon at audit time, but the group is shop-wide (this shop also sells Lorcana and hockey cards). `/page/2` 404s, and pagination is `none` here |
| **Lelukauppa Partanen** | none exists | – | `/category/ennakkotilaukset` loads but lists nothing; `/ennakkotilaukset` 404 |
| **Maxgaming** | none exists | – | `/ennakkotilaukset` and `/kommande` 404. `?instock=0` is ignored: 60 products either way |
| **Muksumassi** | none exists | – | `/ennakkotilaukset/` 404. `/uutuudet/` is new arrivals across the whole shop (prams, car seats), not preorders |
| **Muovijalelu** | none exists | – | `/product-category/ennakkotilaukset/` 404; the `?s=ennakkotilaus` search lists nothing |
| **Muovitukku** | none exists | – | `/tuote-osasto/ennakkotilaukset/` and `/ennakkotilaukset/` 404 |
| **PBCards** | **`/collections/pokemon-pre-orders`** ✅ | 0 | added. Pokémon-scoped (shop title "Ennakkotilaukset") but empty at audit time, confirmed via `products.json`. Its `pagination.url_pattern` was absolute and pinned to `/collections/pokemon`; changed to the query-only `?page={page}` so the preorder URL paginates itself |
| **Pelienmaa** (disabled) | `/collections/pre-order` | 0 | exists, not used: Warhammer preorders (`…-pre-order` product handles), nothing Pokémon, `?filter.p.product_type=Pokémon` empty |
| **Pelikrypta** | none exists | – | `/collections/tuoteryhma-ennakkotilaukset` holds 68 products per `products.json` (36 of them rendered on page 1), all Warhammer, and its `/pokemon` tag filter returns nothing. **Normal coverage fixed:** the configured `/collections/pokemon-trading-card-game` now 404s; `collections.json` gives `/collections/tuoteryhma-pokemon-tcg`, which holds 0 products, so the site contributes nothing until it restocks |
| **Pelimies** | none exists | – | `/tulevat-tuotteet-v2/` exists but lists nothing; `/tuote-osasto/ennakkotilaukset/` 404. The shop's `…ennakkotilaajan-edut` products are video games |
| **Peliparatiisi** | **`/en/collections/pokemon-tcg-ennakkotilaukset`** ✅ | 6 | added. Pokémon-scoped, all 6 named `*ENNAKKOTILAUS*`, `?page=2` empty. `/en/` prefix matches the normal URLs |
| **PokemonCenter** (disabled) | none exists | – | every guessed path answers 200 with no products (SPA shell); the configured URL is already a new-releases feed. Imperva/hCaptcha blocks real fetches |
| **PokePulls** | **`/kategoria/ennakkotilattavissa`** ✅ | 10 | added. Pokémon-scoped, all 10 named `(julkaisu …)`, all carrying the sold-out label. `/page/2/` 404s, pagination is `none` |
| **Poromagia** | none exists | – | `/catalogue/category/ennakkotilaukset/` 404, `/catalogue/?q=ennakko` lists nothing. The `…-preorder` URLs in its sitemap are single MTG cards |
| **Porvoon Pelikauppa** | none exists | – | no preorder category. Preorders sit in the normal categories as products named `…-ennakkotilaus` (4 Pitch Black ones in the sitemap), which is ticket 18's problem |
| **Prisma** | none exists | – | `/ennakkotilaukset` 404. `?ennakkotilaus=1` is ignored: 34 products with and without it, same first items |
| **Proshop** | `/ennakot` | 8 | exists, not used: shop-wide electronics preorders (robot vacuums, cable clips), 0 Pokémon. `?pre=1` on the Pokémon URL is ignored: 19 products either way. Rate-limited (429) on the first two attempts |
| **Puolenkuunpelit** (disabled) | not auditable | – | HTTP 403 on every fetch |
| **Spelexperten** (disabled) | none exists | – | `?Sort=PublDat` only sorts by release date, it does not filter to preorders |
| **Spelparken** | **`/collections/forkop`** ✅ | 8 | added. All 8 Pokémon at audit time, each named `(Förköp) …`, though the collection is shop-wide |
| **Suomalainen** (disabled) | none for Pokémon | – | `/collections/kuumimmat-tulossa-olevat-kirjauutuudet` is upcoming books |
| **Swagykarp** | **`/ennakkotilaukset/`** ✅ | 8 | added. The shop sells only Pokémon, so the category needs no scoping. `/page/2/` serves page 1 again instead of 404ing, so a run re-reads the same 8 up to `max_pages` and logs the "max_pages may be too low" warning; sightings dedupe, so only the extra fetches are real |
| **TCG-kauppa** | **`/ennakkotilaukset/`** ✅ | 27 (20 Pokémon) | added with a known cost: 7 of 27 are Lorcana/World of Tanks and the shop offers no scoping (`?tuote-osasto=pokemon` ignored, `/tuote-osasto/pokemon/?product_cat=ennakkotilaukset` 404s). `/page/2/` is empty, which ends pagination cleanly |
| **Verkkokauppa.com** (disabled) | none found | – | nothing preorder-shaped reachable |
| **VPD** (disabled) | `?ennakkotilaustuote=1` per category | 40 / 1 | a real per-category filter (40 on `boosterit.html`, 1 on `displayt.html`) and the only shop with one that works, but the site is disabled and its names currently parse empty, so nothing added |

**Added:** 7 sites (Korttistoppi, PBCards, Peliparatiisi, PokePulls, Spelparken, Swagykarp, TCG-kauppa).
**Exists but not used:** 8 (Blockhousegames, Ellimadelli, Euro Elite, GodOfCards, Konsolinet,
Pelienmaa, Proshop, VPD), plus KevinsHobbyShop's filter URL that stops filtering on page 2.
**None exists:** 22. **Not auditable:** 2 (Hobbyhall, Puolenkuunpelit, both 403). Total 40.

---

## Why some shop-wide preorder pages were left out

Nothing in the pipeline filters listings by name: whatever a source URL lists becomes a
`listings` row. A shop-wide preorder page therefore imports its Warhammer or electronics
preorders too. The line drawn here: add it if most of what it lists is Pokémon.

| Page | Pokémon share | Verdict |
|---|---|---|
| tcgkauppa `/ennakkotilaukset/` | 20 of 27 | added |
| korttistoppi `/tuoteryhma/ennakkotilaus` | 12 of 12 | added (shop-wide group, all Pokémon today) |
| spelparken `/collections/forkop` | 8 of 8 | added (shop-wide collection, all Pokémon today) |
| blockhousegames `/collections/ennakkotilaukset` | 1 of 24 | left out |
| pelikrypta `/collections/tuoteryhma-ennakkotilaukset` | 0 of 36 on page 1 (68 in `products.json`) | left out |
| proshop `/ennakot` | 0 of 8 | left out |

The three shop-wide pages that were added can drift: a Lorcana or Warhammer preorder wave
would arrive as unmapped listings. Nothing breaks, they just sit unmapped in `listings`.

---

## Filter parameters that turned out to be decoration

Four shops looked like they had a preorder filter. Fetching the same page with and without
the parameter returned identical counts and identical first products, so the parameter is
ignored:

| Shop | Parameter | With | Without |
|---|---|---|---|
| Prisma | `?ennakkotilaus=1` | 34 | 34 |
| Kärkkäinen | `?availability=PreOrder` | 57 | 57 |
| Maxgaming | `?instock=0` | 60 | 60 |
| Proshop | `?pre=1` vs `?pre=0` | 19 | 19 |
| Blockhousegames | `/ennakkotilaukset/pokemon` tag | 24 | 24 |

VPD's `?ennakkotilaustuote=1` is the exception: it really filters (40 vs 16 on the same
category). The site is disabled for unrelated reasons.

---

## Do the normal categories show preorders? (ticket 18 input)

Page 1 of up to three normal source URLs per site, with each site's own availability block
applied (`pass5.py --scan`, `normal_scan.json`). Sites whose names carry a preorder marker:

| Site | Marker in the name | What the availability block reads |
|---|---|---|
| Peliparatiisi | `*PRE-ORDER*`, `*ENNAKKOTILAUS*` (3 items) | `out_of_stock` — the shop puts a "Sold out" badge on preorders |
| Korttistoppi | `(julkaisupäivä …)` (5 items) | `in_stock` |
| Muksumassi | `(julkaisupäivä …)` (2 items) | `in_stock` |
| Ellimadelli | `- Ennakkotilaus` (1 item) | `in_stock` |
| PokePulls | none in the normal categories | its 10 preorders live only on the preorder URL, all sold-out-labelled |

Every other site showed no preorder marker in any listing name on page 1. Two readings are
possible and this audit cannot separate them: either the shop hides preorders from its
normal categories, or it lists them with no textual marker at all. Either way a badge-only
signal is not visible in the name, which is what ticket 18 has to solve.

The preorder-URL flag matters exactly because of the middle column: on the pages that were
added, badges read `out_of_stock` (swagykarp 6 of 8, pokepulls 10 of 10, peliparatiisi 6 of
6) or `in_stock` (korttistoppi 12 of 12, spelparken 8 of 8). Neither is `preorder`, so
without the flag outranking the forms the state would be wrong on every one of them.

---

## Normal-coverage findings from the same pass

- **Pelikrypta:** configured `source_url` 404s; replaced with `/collections/tuoteryhma-pokemon-tcg`
  (0 products in it today, so the site is effectively dark until it restocks). `sites` rows are
  keyed on the first normal source URL (`runner._upsert_site`), so on an existing database this
  swap inserts a second Pelikrypta row instead of reusing the old one. Moot for the refocus DB,
  which `scripts/rebuild_db.py` builds from scratch; on any DB carried over, update
  `sites.url` by hand before the next run.
- **PBCards:** absolute `pagination.url_pattern` pinned to `/collections/pokemon` replaced by
  the query-only `?page={page}`. Same result for the collection, and it no longer walks a
  second URL back into the first.
- **GodOfCards:** the normal URL is `…/english-pokemon-cards?filter.v.availability=1`, i.e.
  in-stock only. The `availability=0` variant shows 32 out-of-stock products that the tracker
  never sees, so `back_in_stock` can never fire for this shop. Left as-is on purpose: the
  site has no availability block, so importing those 32 would only add `unknown` rows, while
  the filter at least makes disappearance mean "out of stock". Ticket 18 should decide.
- **Spelparken:** prices parse as `2.599` and `449.0` from SEK amounts, i.e. the thousands
  separator is read as a decimal point. Pre-existing, unrelated to this ticket.
- Sites unreachable during the pass: Hobbyhall (403), Puolenkuunpelit (403), Keräilykortti
  (intermittent timeouts, answered on the third try), Proshop (429 twice).
