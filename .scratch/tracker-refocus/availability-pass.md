# Availability pin-down pass — ticket 18

What was checked, per site: the live listing HTML, the elements that carry a
state, the block that went into the config, and the split that block produces.
Splits are from the live `python -m scraper.probe --all` run recorded in
`probe_all_after.log` (before it: `probe_all_before.log`).

Method for a single site:

1. `python -m scraper.probe site_configs/<site>.json` for the badge census.
2. `badges.py` for the tag names and class lists behind those texts, `wordscan.py`
   for every state wording inside a product container across cached pages.
3. Write the block with `set_block.py`, then `split.py` to re-read every cached
   page offline instead of re-fetching 29 shops per edit.
4. Where the Pokemon listing showed one state only, fetch a busier page from the
   same shop (another category, `?sort_by=best-selling`, `/collections/all`, the
   shop's own search) or compare against Shopify's `products.json`, which reports
   `available` per variant and so tells the truth about a page showing no
   sold-out cards at all.

## Sites with a block

### blockhousegames.net — Blockhouse Games
- Found: `.product-item__inventory` reads `Saatavilla <n>` in stock and
  `Loppuunmyyty` sold out. The element is present in **both** states, and its
  class only differs by a `--high` suffix that sold-out cards also sometimes
  carry, so the migrated presence check read sold-out cards as in stock.
- Block: `text_map` on `Loppuunmyyty` / `Saatavilla`, `default: unknown`.
- Split: 24 in stock, 0 sold out on the Pokemon collection.
- Checked on `/collections/all?sort_by=best-selling`: 12 in stock, 12 sold out.
- **Tracked in-stock-only**: 0 of 28 products in the configured collection are
  sold out; the shop drops sold-out items from that collection.
- Fixture: `tests/fixtures/blockhousegames.net/availability.html` (4 + 4).

### casagrande.fi — Casagrande
- Found: `span.label.label--subdued` `Tilapäisesti loppu` on 7 of 47 cards, no
  label otherwise.
- Block: unchanged from ticket 15 (`presence` on `.label--subdued`), confirmed.
- Split: 41 in stock, 7 sold out.

### ellimadelli.fi — Elli Madelli
- Found: `.product-stock-level--high` / `--low` on in-stock cards, nothing on
  sold-out cards.
- Block: unchanged (`presence` on both level classes), confirmed against
  `/collections/all?sort_by=best-selling` (14 in stock, 10 sold out).
- Split: 24 in stock, 0 sold out.
- **Tracked in-stock-only**: 0 of 141 products in the configured collection are
  sold out.
- Preorder wording appears in product *names* only ("ennakko"), and nothing in
  the pipeline reads names, so it is not mapped.

### fantasialinna.com — Fantasialinna
- Found: `div.stock` reads `Varastossa` or `Väliaikaisesti loppu`. The old
  `.in-stock` selector named in the ticket does not exist on the live pages.
- Block: `text_map` on both wordings, `default: unknown`.
- Split: 12 in stock, 0 sold out on page 1; page 3 reads 10 in stock, 2 sold out.
- Fixture: `tests/fixtures/fantasialinna.com/availability.html` (4 + 2, page 3).

### flea.fi — Flea Lelukauppa
- Found: `.tt-label-our-stock` `Tilapäisesti loppu` on sold-out cards; the
  add-to-cart form (`form[action='/cart/add']`) is missing on the same cards.
- Block: `text_map` for the badge, `presence` on the form as the fallback, and no `default`:
  the presence check sets both `present` and `absent`, so a default is unreachable.
- Split: 8 in stock, 1 sold out. Two independent signals agree on that one card.

### godofcards.com — God of Cards
- Found: `.badge--sold-out` `Sold out`, plus `form.shopify-product-form` present
  only when buyable.
- Block: `text_map` plus `presence` on the form.
- Split: 27 in stock, 0 sold out, with `[no matches: .badge--sold-out]`.
- The marker is legitimate: the source URL carries `filter.v.availability=1`, so
  the listing is filtered to in-stock items. The unfiltered
  `/en-fi/collections/english-pokemon-cards` reads 27 in stock, 5 sold out with
  the same block.
- **Tracked in-stock-only**, and self-inflicted: the filter is in our own source URL, not the
  shop's markup. Dropping `filter.v.availability=1` would make sold-out items visible, but the
  site row is keyed on the exact first source URL (`_upsert_site` in `scraper/runner.py`), so
  the change re-keys the site and orphans its listing history. Left for a coverage ticket
  rather than done quietly here.
- No `default` in the block: the presence check sets both branches.

### kerailykortti.fi — Keräilykortti.fi
- Found: no state text anywhere inside a card; the WooCommerce container classes
  carry it (`instock` on 30, `outofstock` on 39 across three cached pages).
- Block: unchanged `container_class_map`, confirmed.
- Split: 30 in stock, 39 sold out.

### kevinshobbyshop.com — Kevin's Hobby Shop
- Not verifiable from here: every request answers HTTP 403, including the front
  page, so no HTML could be read at all.
- Block: `container_class_map` left as migrated. The class names are WooCommerce
  defaults, which is the strongest guess available without the page.
- Split: 0 listings, `[HTTP 403 ...]` on the `--all` line.

### kodintavaratalo.fi — JR Kodintavaratalo
- Found: `.out-of-stock` `Tilapäisesti loppu` on sold-out cards, absent on
  in-stock cards.
- Block: `presence` on `.out-of-stock`.
- Split: 24 in stock, 0 sold out, with `[no matches: .out-of-stock]`.
- The marker is legitimate: the whole Pokemon listing is in stock. Checked on
  `/lego`, which reads 14 in stock, 10 sold out.
- Fixture: `tests/fixtures/kodintavaratalo.fi/availability.html` (4 + 4, /lego).

### karukortti.fi — KaruKortti
- Found: `.product-sold-out-label` `Sold out` on 22 of 34 cards, nothing on the
  rest.
- Block: unchanged `presence`, confirmed.
- Split: 25 in stock, 40 sold out (65 listings).
- Unrelated open problem: every KaruKortti price is rejected as suspicious
  (`'€359.95'` parses as 35995 under the site's `decimal_separator`), so the site
  produces no priced readings. Out of scope here, worth its own ticket.

### korttistoppi.fi — Korttistoppi
- Found: `.product-badge-content` reads `Loppunut` (sold out) or `Ennakkomyynti`
  (preorder); no badge means in stock.
- Block: `text_map` for both, `default: in_stock`.
- Split: 59 in stock, 277 sold out, 22 preorder (358 listings).

### lelupartanen.fi — Lelukauppa Partanen
- Found: an unclassed `p.MuiTypography-body2` reading `Heti saatavilla` or
  `Vain Jyväskylän myymälässä` (in the Jyväskylä shop only, not orderable).
- Block: `text_map` on both, `default: unknown`.
- Split: 52 in stock, 8 sold out.
- Fixture: `tests/fixtures/lelupartanen.fi/availability.html` (4 + 4).

### maxgaming.fi — MaxGaming
- Found: `.PT_text_Lagerstatus` carries four wordings: `Varastossa`,
  `Loppuunmyyty`, `Loppu varastosta`, `Tulossa pian` (preorder).
- Block: `text_map` with all four, `default: unknown`.
- Split: 12 in stock, 38 sold out, 10 preorder.
- Fixture: `tests/fixtures/maxgaming.fi/availability.html` (4 + 4 + 4) — the only
  fixture in the suite carrying all three states.

### muksumassi.fi — Muksumassi
- Found: WooCommerce container classes only. `instock` on every Pokemon card;
  `onbackorder` turns up on other listings, and such a product's page says
  `Ei varastossa, vain jälkitoimituksena`.
- Block: `container_class_map` with `onbackorder` added as `out_of_stock`.
- Split: 59 in stock, 0 sold out.
- **Tracked in-stock-only**: 0 of 143 cards on the shop's own Pokemon search and
  0 of 40 on `/kauppa` carry `outofstock`.

### muovijalelu.fi — Muovi ja Lelu
- Found: `p.stock.in-stock` `Varastossa` (the woo-custom-stock-status plugin) on
  every card, and the WooCommerce `instock` container class alongside it.
- Block: unchanged `presence` on `p.stock.in-stock`.
- Split: 35 in stock, 0 sold out.
- **Tracked in-stock-only**: no sold-out card appeared on any page checked (the
  Pokemon search, `joulukalenteri`, `lastentarvikkeet`; 105 cards), so the
  `absent` branch is unverified rather than wrong.

### muovitukku.fi — Muovitukku
- Found: `.tuoteslideri-meta.is-green` `Saatavilla myymälästä` / `toimitus` on 18
  cards, `.is-red` `Ei saatavilla` on 12.
- Block: unchanged `presence` on `.is-green`, confirmed.
- Split: 18 in stock, 12 sold out.

### pbcards.fi — PBCards
- Found: `p.stock.overlay-valid` `20+ varastossa` / `9 varastossa` etc. versus
  `p.stock.overlay-error` `Ei varastossa`; sold-out containers also carry the
  `unavailable` class.
- Block: unchanged `presence` on `.stock.overlay-valid`, confirmed.
- Split: 6 in stock, 6 sold out.

### pelikrypta.fi — Pelikrypta (Ikamaa)
- Found: `.card__badge .badge` `Loppuunmyyty` on sold-out cards (Shopify Dawn).
- Block: `text_map` on `Loppuunmyyty`, `default: in_stock`.
- Split: 0 listings — the configured collection is empty (recorded in ticket 17).
  Checked on `/collections/all?sort_by=best-selling`: 35 in stock, 1 sold out.

### pelimies.fi — Pelimies
- Found: `.tag-future` `Tuleva julkaisu` on preorder cards, which also carry a
  working add-to-cart button, so presence alone read them as in stock.
- Block: `text_map` for the tag first, then `presence` on `a.add_to_cart_button`.
- Split: 35 in stock, 0 sold out, 6 preorder.
- **Tracked in-stock-only**: 0 of 1500 cards on `/kauppa?orderby=popularity` are
  sold out; the shop hides sold-out products from its catalogue. The only cards
  without a cart button are variable products ("Lue lisää"), of which there are 3
  in 1500 and none in the Pokemon listing; those would read `out_of_stock`.
- Fixture: `tests/fixtures/pelimies.fi/availability.html` (4 in stock + 4
  preorder).

### peliparatiisi.net — Peliparatiisi
- Found: `span.badge` `Sold out` on 27 of 33 cards.
- Block: unchanged `text_map`, `default: in_stock`, confirmed.
- Split: 10 in stock, 75 sold out (85 listings).
- Preorder wording appears in names only, so it is not mapped (same as
  ellimadelli.fi).

### pokepulls.fi — PokePulls
- Found: `span.product-sold-out-label` on sold-out cards (same platform as
  karukortti.fi).
- Block: unchanged `presence`, confirmed.
- Split: 30 in stock, 53 sold out (83 listings).

### poromagia.com — Poromagia
- Found: `p.availability` reads `Julkaisupäivä <date>` for preorders; in-stock
  cards carry the WooCommerce `.instock.availability` element.
- Block: `text_map` on `Julkaisupäivä`, then `presence` on `.instock.availability`.
- Split: 59 in stock, 7 sold out, 2 preorder (68 listings).

### porvoonpelikauppa.fi — Porvoon Pelikauppa
- Found: `.out-of-stock` present on sold-out cards.
- Block: unchanged `presence`, confirmed.
- Split: 67 in stock, 11 sold out (78 listings).
- Not mapped: the free-text `Julkaisu <date>` in card descriptions. Dates that
  have already passed are still shown (07/08/2026 among them), so reading it as
  preorder would strand released products in that state.

### prisma.fi — Prisma.fi
- Found: the sold-out text `Ei saatavilla` sits in `.bg-color-background-error`.
  The migrated selector was `.background-error p`, which matches nothing, so
  every listing fell through to `default: in_stock`.
- Block: same `text_map`, selector corrected.
- Split: 32 in stock, 2 sold out; the saved fixture reads 29 and 4.
- Fixture test added on the existing `tests/fixtures/prisma.fi/page1.html`.

### proshop.fi — Proshop
- Found: `.site-icon-stock-in` next to `Varastossa - 2-5 arkipäivän toimitus`
  (12 cards) and `Tukkurilla, N arkipäivää toimitukseen` (2);
  `.site-icon-stock-comming` next to `Tilaustuote, toimitusaikaa ei voida
  ilmoittaa` (5).
- Block: unchanged `presence` on `.site-icon-stock-in`, confirmed. The
  `stock-comming` case reads `out_of_stock`, not preorder: it is an order-in
  product with no delivery estimate and no release date.
- Split: 14 in stock, 5 sold out.

### spelparken.se — Spelparken
- Found: `.card__badge .badge` `Slutsåld` on 3 of 47 cards (each rendered twice
  in the markup, which is why a raw badge count says 6). No cart form on the
  cards, so presence is not available as a signal here.
- Block: unchanged `text_map` on `Slutsåld`, `default: in_stock`, confirmed. None of the
  Swedish preorder wordings (`kommer`, `släpp`, `förköp`) appears anywhere inside a product
  card, so there is nothing to map to preorder here.
- Split: 79 in stock, 4 sold out (83 listings). Three of the four are on page 1,
  which is the page the earlier counts above describe.

### swagykarp.fi — Swagykarp
- Found: `.acoplw-blockText` carries `Pre order` on preorder cards **and**
  `Out of Stock` on sold-out cards; containers also carry the WooCommerce
  `instock` / `outofstock` classes.
- Block: `text_map` maps `Pre order` only, then `container_class_map`. Mapping
  `Out of Stock` as well would break preorder: the parser takes the longest
  matching key across all matched elements, and `Out of Stock` is longer than
  `Pre order`, so preorder cards would resolve to sold out.
- Split: 49 in stock, 14 sold out, 8 preorder (71 listings).
- Fixture: `tests/fixtures/swagykarp.fi/availability.html` (3 + 2 + 2), with
  tests pinning both the preorder text and the class the sold-out reading comes
  from.

### tcgkauppa.fi — TCG-kauppa
- Found: `div.fusion-out-of-stock` `Ei varastossa` on 103 of 132 cards, plus the
  container classes `instock`, `outofstock` and `insufficientstock` (28, always
  together with `outofstock` today).
- Block: `container_class_map` with `insufficientstock` added as `out_of_stock`,
  so a card carrying it alone cannot fall through to unknown.
- Split: 42 in stock, 350 sold out (392 listings).

## Sites without a block

### karkkainen.com — Karkkainen.com verkkokauppa (untracked)
Every one of the 57 listing cards carries
`data-ls-availability="OutOfStock"` on `.lipscore-rating-small`, including items
whose own product page says `InStock`, and the cards are otherwise identical:
no badge, no differing class, no cart form. The attribute is Lipscore review
markup, not stock. The migrated block read all 57 as sold out, which is worse
than reading nothing, so the block is dropped and the app shows the site as not
tracked. Price and name still work, so the site keeps contributing listings.

Guarded by `test_karkkainen_is_not_tracked`, which asserts
`availability_forms(config) is None` and that every reading is `unknown`.

### The 11 disabled configs
None of them has an availability block and none can get one: the config is
disabled because the site cannot be scraped at all from here. Reasons as
recorded in `disabled_reason`:

| Site | Reason |
|---|---|
| cdon.fi | JS-rendered (React + lazy load); plain requests returns placeholder HTML |
| euroelite.fi | Operator decision to drop the site (mixed content, 9 products) |
| hobbyhall.fi | Brand page mixes TCG with unrelated merchandise; no stock signal |
| konsolinet.fi | JS bot check (Client Challenge) on plain fetch |
| pelienmaa.com | Blocked by the corporate proxy on this machine |
| pokemoncenter.com | Imperva/hCaptcha on every request |
| puolenkuunpelit.com | Blocked by the corporate proxy on this machine |
| spelexperten.fi | No sealed-only category URL; operator decision |
| suomalainen.com | Algolia InstantSearch, products appear only after JS |
| verkkokauppa.com | Hashed class names change per deploy; no in-stock signal on tiles |
| vpd.fi | Not yet verified reachable from the server |

Three of the four "cheapest four" the ticket lists are in this table
(euroelite.fi, konsolinet.fi, vpd.fi), so their old `in_stock` selectors stay
deleted. The fourth, fantasialinna.com, is done above and the selector the ticket
quotes turned out not to exist on the live page.

## Coverage, read honestly

29 configs are enabled. 27 carry a block that was checked against live HTML,
1 (kevinshobbyshop.com) carries a block that could not be checked because the
shop answers 403, and 1 (karkkainen.com) is deliberately untracked.

Six of the 27 are **tracked in-stock-only**: blockhousegames.net, ellimadelli.fi,
godofcards.com, muksumassi.fi, muovijalelu.fi and pelimies.fi. Their listing
pages do not show sold-out products at all (either the shop hides them or the
configured URL filters them out), so a 100% in-stock split there means "every
product still listed is in stock", not "nothing has sold out". A product going
out of stock at these shops shows up as a listing that disappears, and reading a
disappearance as out of stock is ruled out in the spec's Out of Scope, so the
tracker will simply stop seeing it.

Preorder now reads as preorder on five sites that previously showed none:
korttistoppi.fi (22), maxgaming.fi (10), pelimies.fi (6), poromagia.com (2),
swagykarp.fi (8), plus the preorder-URL sites from ticket 17.

## Parser change

`container_class_map` recorded the container's whole class list as
`availability_text`, capped at 120 chars. Swagykarp cards carry about 20 classes
and `instock` sits past the cap, so the stored diagnostic lost the one class that
decided the state. It now records the full list when it fits and the matched
class alone when it does not
(`test_container_class_map_records_the_matched_class_when_the_list_is_long`).

## Helper scripts used

All under `.scratch/tracker-refocus/`, none of them part of the pipeline:
`fetch_pages.py` (cache page 1-3 of every enabled config once), `badges.py`
(tag + class + text census inside containers), `wordscan.py` (every state wording
per site), `split.py` (the probe census over cached pages, offline),
`shopify_check.py` (config reading versus Shopify `products.json`),
`set_block.py` / `add_note.py` (config edits keeping key order and note style),
`trim_fixture.py` (cut a cached page to a few containers per state for a
fixture).
