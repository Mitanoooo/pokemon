# Site-Specific Scraper Notes

This file is the authoritative reference for quirks, gotchas, and special handling needed per site.
It is built incrementally as each batch is validated. Feed this into the scraper build session.

---

## How to read this file

Each entry has:
- **Status**: `validated` (prototype confirmed working) | `pending` (config exists, not yet tested) | `broken` (needs fix)
- **Price handling**: any cleanup needed on the raw price string
- **Stock logic**: how to interpret the in_stock selector (normal / inverted / container-class)
- **Pagination**: confirmed page count and URL pattern
- **Notes**: anything else the scraper must know

---

## Batch 1 — validated

### casagrande.fi
- **Status**: validated — 49 products, 1 page
- **Price handling**: Raw text contains "Alennushinta" prefix (Finnish for "sale price") — strip all non-numeric/decimal/currency characters, keep only the number and € symbol. Extract last price value if multiple.
- **Stock logic**: INVERTED — presence of `.label--subdued` inside container = OUT OF STOCK. Absence = in stock.
- **Pagination**: none (all 49 products on one page)
- **Notes**: Shopify theme. Works cleanly with requests+BS4.

---

### ellimadelli.fi
- **Status**: validated — 138 products across 6 pages
- **Price handling**: Clean — price text is plain `"14,95 €"` format, no cleanup needed.
- **Stock logic**: Normal — presence of `.product-stock-level--high` or `.product-stock-level--low` = in stock. Neither present = out of stock. Note: out-of-stock variant class not confirmed (no out-of-stock products seen during validation).
- **Pagination**: url_pattern confirmed, 6 pages: `?page={page}&grid_list=grid-view`
- **Notes**: Shopify Impulse/Prestige theme. Works cleanly with requests+BS4.

---

### poromagia.com
- **Status**: validated — 76 products across 4 pages
- **Price handling**: Clean — `"21,95 €"` format.
- **Stock logic**: Normal — `.instock.availability` present = in stock. Absence = out of stock. Stock detection confirmed working (both in-stock and out-of-stock products observed).
- **Pagination**: url_pattern confirmed, 4 pages: `?page={page}`
- **Notes**: Page contains a "SUOSITTUA" (popular) widget above the main listing using `article.product_pod` — scraper must only use `article.product_line` to avoid duplicates. Works cleanly with requests+BS4.

---

### porvoonpelikauppa.fi
- **Status**: validated — 24 products, 1 page
- **Price handling**: Clean — `"49,85 €"` format. One product showed `"1,00 €"` which appears to be a placeholder price — worth flagging suspiciously low prices (< 2 €) in the scraper log.
- **Stock logic**: INVERTED — presence of `.out-of-stock` inside container = OUT OF STOCK. Absence = in stock. Confirmed working (both states observed).
- **Pagination**: none (all 24 products on one page)
- **Notes**: Custom Finnish webshop platform. Works cleanly with requests+BS4.

---

### tcgkauppa.fi
- **Status**: validated — 214 products across 5 pages
- **Price handling**: Raw text can contain TWO prices (original + sale): `"4,90 € 3,90 €"` — always extract the LAST price value (the sale/current price).
- **Stock logic**: CONTAINER CLASS — check the `product_container` element's own class list for `"instock"` (not a descendant selector). `"instock"` in container classes = in stock; `"outofstock"` = out of stock.
- **Pagination**: url_pattern confirmed, 5 pages: `/page/{page}/`. Page 1 has no `/page/1/` suffix — use base URL for page 1, pattern for pages 2+.
- **Notes**: Standard WooCommerce (Avada theme). Works cleanly with requests+BS4.

---

## Batch 2 — validated

### muksumassi.fi
- **Status**: validated — 34 products, 1 page
- **Price handling**: Clean — `"14,95€"` format (no space before €, but parseable fine).
- **Stock logic**: CONTAINER CLASS — `li.product` carries `instock` or `outofstock` directly in its own class list. Same pattern as tcgkauppa.fi. All 34 products were `instock` during validation.
- **Pagination**: none (1 page confirmed)
- **Notes**: WooCommerce with Bricks builder theme. Works cleanly with requests+BS4. Confirmed 34 containers.

---

### maxgaming.fi
- **Status**: validated — 184 products across 4 pages
- **Price handling**: Uses dot as decimal separator (`"219.90 €"`) — different from all other Finnish sites. Price parser must handle both comma and dot formats.
- **Stock logic**: Normal — `.Lager_1_FI` present inside container = in stock. Other classes `Lager_2_FI`, `Lager_10_FI`, `Lager_12_FI` = out of stock/unavailable. During validation all sampled items showed no `.Lager_1_FI` (out of stock). Selector targets the specific in-stock class.
- **Pagination**: url_pattern confirmed, 4 pages: `?page={page}`. Pages 1–3 have 60 products each, page 4 has 4.
- **Notes**: Product name `.PT_Beskr` contains two lines: first line is always `"Pokémon"` (brand), second line is the actual product title. Use `get_text()` and strip/split on lines — take the last non-empty line, or strip the `"Pokémon\n"` prefix. Custom platform, not WooCommerce/Magento/Shopify.

---

### vpd.fi
- **Status**: BROKEN — JS skeleton loader; requests+BS4 returns empty skeleton markup, 0 real product content
- **Price handling**: N/A until JS rendering resolved
- **Stock logic**: `.stock-status.available` per config — not validated
- **Pagination**: 11 pages with `?p={page}` — not validated
- **Notes**: Magento 2 site with client-side skeleton loading. All 40 containers were empty placeholders (`product-slider-skeleton__box`). **Requires Playwright** to render the product grid. Flag for Playwright fallback in production scraper.

---

### korttistoppi.fi
- **Status**: validated — 67 products, 1 page
- **Price handling**: Clean — `"219,90 €"` format.
- **Stock logic**: INVERTED (badge-based) — presence of `.product-badge-content` with text `"Loppunut"` inside container = OUT OF STOCK. In production scraper: `in_stock = container.select_one('.product-badge-content') is None or container.select_one('.product-badge-content').get_text(strip=True) != 'Loppunut'`. Stock state not confirmed during validation (no out-of-stock products observed).
- **Pagination**: none (1 page, `Sivu 1 / 1` confirmed)
- **Notes**: Finqu platform. Works cleanly with requests+BS4.

---

### pokepulls.fi
- **Status**: validated — 16 products, 1 page
- **Price handling**: Clean — `"18,90 €"` format.
- **Stock logic**: INVERTED (badge-based) — presence of `.product-sold-out-label` inside container = OUT OF STOCK. Absence = in stock. Stock state not confirmed during validation (no out-of-stock products observed).
- **Pagination**: none detected (no pagination controls visible). Site may use client-side filtering or infinite scroll — monitor for missed products.
- **Notes**: Next.js/Tailwind storefront (SumUp/Storefront platform). Selectors use `data-selector` attributes which are more stable than utility classes. Works cleanly with requests+BS4 for visible products. Medium confidence from Copilot.

---

## Batch 3 — validated

### puolenkuunpelit.com
- **Status**: BLOCKED — Cloudflare 403 ("Just a moment..."). Requests+BS4 cannot pass.
- **Price handling**: N/A
- **Stock logic**: N/A
- **Pagination**: N/A
- **Notes**: Cloudflare bot protection blocks all non-browser requests. **Skip this site** — user agreed that problem sites can be dropped. Mark as `disabled` in production config.

---

### swagykarp.fi
- **Status**: partially validated — 12 products on page 1 only (prototype doesn't follow `next_button` pagination). 5 pages confirmed, ~54 products total.
- **Price handling**: Price contains non-breaking space `\xa0` before `€` (e.g. `"17,00\xa0€"`). Normalise `\xa0` → regular space during price cleanup.
- **Stock logic**: CONTAINER CLASS — `li.product` carries `instock` or `outofstock` in its own class list. Confirmed both states observed during validation (e.g. `151 Booster Pack` = outofstock).
- **Pagination**: `next_button` type. Actual URL pattern is `https://swagykarp.fi/product-category/pokemon-tuotteet/boosterit/page/{page}/`, 5 pages. Production scraper should follow `next_button` href or use this url_pattern.
- **Notes**: Standard WooCommerce. Works cleanly with requests+BS4.

---

### kerailykortti.fi (xn--kerilykortti-icb.fi)
- **Status**: partially validated — selectors work, but **config `source_url` is wrong**: it points to the homepage `/` which shows carousel widgets with duplicate items and price blobs. Correct `source_url` is `https://www.xn--kerilykortti-icb.fi/kauppa/` (16 products/page × ~5 pages).
- **Price handling**: Price `span.price` can contain `<del>` (original) + `<ins>` (sale) children. Extract `ins .woocommerce-Price-amount` when present, fall back to `.woocommerce-Price-amount` for non-sale items. Also strip `\xa0` (non-breaking space).
- **Stock logic**: CONTAINER CLASS — `li.product` carries `instock` or `outofstock`. Confirmed both states during validation.
- **Pagination**: url_pattern: `https://www.xn--kerilykortti-icb.fi/kauppa/page/{page}/`. Approximately 5 pages.
- **Notes**: Standard WooCommerce. **Fix config `source_url` to `/kauppa/`** before production scraper build.

---

### prisma.fi
- **Status**: validated — 33 products, 1 page ✅
- **Price handling**: Clean — `"40,50 €"` format.
- **Stock logic**: INVERTED (badge-based) — presence of `<p>` with text `"Ei saatavilla"` inside card = OUT OF STOCK. Absence = in stock. Stock state not confirmed during validation.
- **Pagination**: none (33 products, no pagination controls)
- **Notes**: Custom Next.js/S-kauppa storefront. Selectors use stable `data-test-id` attributes. A "Suosituimmat tuotteet" horizontal carousel at top uses the same selectors — scope product_container to `ul[data-test-id='brand-product-list'] li` in production scraper to avoid duplicate carousel matches. Works cleanly with requests+BS4.

---

### verkkokauppa.com
- **Status**: BROKEN — JS skeleton loader. Requests+BS4 returns 48 placeholder `article[data-product-id="0"]` containers with empty names, `"0,00"` prices, and loading placeholder text. Zero real product data.
- **Price handling**: N/A until JS rendering resolved
- **Stock logic**: N/A
- **Pagination**: N/A
- **Notes**: Next.js site with client-side data loading. Same pattern as vpd.fi. **Requires Playwright**. User agreed that problem sites can be dropped — flag for Playwright fallback or skip.

---

## Batch 4 — validated

### blockhousegames.net
- **Status**: validated — 28 products across 2 pages ✅
- **Price handling**: Price element contains a `.visually-hidden` span (`"Alennushinta"`) before the amount, and uses `EUR` suffix instead of `€` symbol. Raw: `"Alennushinta€59,90 EUR"`. Scraper must: (1) decompose/strip `.visually-hidden` child before reading text, (2) strip `EUR` and normalise to `€`. Result: `"59,90 €"`.
- **Stock logic**: Normal — `.product-item__inventory` present = in stock. Absence likely = out of stock (not confirmed against a live out-of-stock item — treat absence as out-of-stock but flag for manual verification).
- **Pagination**: url_pattern `?page={page}` is relative — config must prepend base URL. Full pattern: `https://blockhousegames.net/collections/pokemon-tcg?page={page}`. 2 pages (24 + 4 = 28 products).
- **Notes**: Shopify Impulse theme. Works cleanly with requests+BS4.

---

### karkkainen.com
- **Status**: validated — selectors work but price/stock are in **HTML attributes, not text** ✅
- **Price handling**: Price is NOT in rendered text. Read `data-ls-price` attribute from `.lipscore-rating-small` element (e.g. `data-ls-price="6.49"`). Value uses dot decimal, no currency symbol — treat as EUR float.
- **Stock logic**: Read `data-ls-availability` attribute from same `.lipscore-rating-small` element. Value is `"InStock"` or `"OutOfStock"`. Both confirmed during validation.
- **Pagination**: Offset-based, NOT page-number-based. Correct formula: `?offset={(page-1)*60}`. Page 2 = `?offset=60`, page 3 = `?offset=120`. Config's `url_pattern` placeholder `{offset}` was wrong (used page number). 66 total products → 2 pages (60 + 6).
- **Notes**: React/MUI server-side rendered. Category is general "Keräilykortit" — includes ~60 total products of which ~12 are Pokemon. Production scraper must filter by `data-ls-category` containing `"Keräilykortit"` and product name containing `"Pokemon"`, or use a Pokemon-specific URL if one exists. `data-ls-product-url` attribute provides the absolute product page URL — use it instead of constructing from href.

---

### karukortti.fi
- **Status**: validated — 8 products, 1 page ✅. Both in-stock and out-of-stock confirmed.
- **Price handling**: Clean — `"349,95 €"` format.
- **Stock logic**: INVERTED (badge-based) — same platform as pokepulls.fi (SumUp/os-theme). Presence of `.product-sold-out-label` inside container = OUT OF STOCK. Confirmed working: 1 in-stock, 7 out-of-stock during validation.
- **Pagination**: none (8 products, 1 page confirmed despite `<link rel="next">` in `<head>` — page 2 returns zero products)
- **Notes**: SumUp/os-theme storefront. `product_container` is the `<a>` tag itself — `href` attribute = product URL directly. Works cleanly with requests+BS4.

---

### kevinshobbyshop.com
- **Status**: validated — selectors work ✅, but **page count must be capped**
- **Price handling**: Price uses `€` prefix before the number (e.g. `"€195,00"`) rather than `€` suffix. Parser must handle both `"34,90 €"` and `"€195,00"` formats.
- **Stock logic**: CONTAINER CLASS — `li.product` carries `instock` or `outofstock` in its own class list. Confirmed both states during validation.
- **Pagination**: url_pattern `/shop/page/{page}/?yith_wcan=1&filter_game=pokemon&query_type_game=or` is relative — prepend `https://kevinshobbyshop.com`. **Config claims 179 pages** — this covers all TCG singles. Cap at `max_pages: 5` in production to get sealed product pages only (sealed items appear first), or add category URL for sealed products specifically.
- **Notes**: WooCommerce with YITH filter. Works cleanly with requests+BS4.

---

### pokemoncenter.com
- **Status**: BLOCKED — hCaptcha "I am human" challenge on every request. Zero product HTML reachable.
- **Price handling**: N/A
- **Stock logic**: N/A
- **Pagination**: N/A
- **Notes**: Imperva/Incapsula + hCaptcha protection. Cannot be scraped with requests or headless browser without solving CAPTCHA. **Skip this site.**

---

## Batch 5 — validated

### spelparken.se
- **Status**: validated — 22 products across 2 pages ✅
- **Price handling**: Swedish krona (`kr`), not euros. Raw: `"5 499 kr"` with spaces as thousands separators. Do NOT use `.price` full text (duplicated blob). Use `.price-item--sale` directly. Store as SEK — not EUR.
- **Stock logic**: INVERTED (badge text) — `.card__badge .badge` with text `"Slutsåld"` = OUT OF STOCK. Badge may also contain `"Nyhet"` (new) or sale text — check text equals `"Slutsåld"` exactly.
- **Pagination**: url_pattern confirmed, 2 pages: `?page={page}` (absolute URL)
- **Notes**: Shopify Dawn theme. Swedish-language site (prices in SEK). Works cleanly with requests+BS4.

---

### pelienmaa.com
- **Status**: validated — 7 products, 1 page ✅. Copilot gave null selectors (corporate network block) but site works normally.
- **Price handling**: Same as blockhousegames.net — `€379,90 EUR` format. Strip `.visually-hidden` spans, strip `EUR` suffix and `€` prefix, normalise to float.
- **Stock logic**: INVERTED (badge text) — `.card__badge .badge` with text `"Loppuunmyyty"` = OUT OF STOCK. All 7 products were out of stock during validation.
- **Pagination**: none (7 products, 1 page)
- **Notes**: Shopify Dawn theme. **Config needs correction** — all selectors were null. Correct selectors: `product_container: li.grid__item`, `product_name: h3.card__heading a`, `price: .price-item--sale` (fallback `.price-item--regular`), stock badge inverted text check.

---

### proshop.fi
- **Status**: validated — 21 products, 1 page ✅. One corrupted demo price.
- **Price handling**: Clean `"27,90 €"` for normal items. `\xa0` used as thousands separator (e.g. `"1\xa0394\xa0072,10 €"` on demo item). Strip `\xa0`. Ignore `.hidden-xs` element (ex-VAT price). Flag prices above ~2000 € as suspicious/demo.
- **Stock logic**: Normal — `.site-icon-stock-in` present = in stock. Other classes (`site-icon-stock-comming` etc.) = not purchasable, treat as out of stock.
- **Pagination**: none (21 products, 1 page)
- **Notes**: Custom Nordic Proshop platform. Works cleanly with requests+BS4.

---

### kodintavaratalo.fi
- **Status**: validated — 24 products, 1 page ✅
- **Price handling**: Clean — `"37,95 €"` format.
- **Stock logic**: UNKNOWN — no stock indicator on listing page. Set `in_stock: null`.
- **Pagination**: none (24 products, 1 page)
- **Notes**: Custom Finnish webshop. Works cleanly with requests+BS4.

---

### suomalainen.com
- **Status**: BROKEN — Algolia InstantSearch client-side rendering. Zero `li.ais-Hits-item` in static HTML.
- **Price handling**: N/A
- **Stock logic**: N/A
- **Notes**: Primarily a bookstore; Pokemon collection is mostly books/merch, not TCG sealed product. **Requires Playwright or Algolia API. Low priority — skip.**

---

## Batch 6 — validated

### konsolinet.fi
- **Status**: BROKEN — JS bot-check stub. Requests+BS4 returns a ~3KB client challenge page, zero product HTML.
- **Price handling**: N/A
- **Stock logic**: N/A (config notes: container-class `AvailabilityInStock`/`AvailabilityOutOfStock`)
- **Notes**: Custom Finnish platform with JS bot challenge on every request. **Requires Playwright.** Flag for Playwright fallback or skip.

---

### spelexperten.fi
- **Status**: validated — 346 products across 11 pages ✅
- **Price handling**: `€` prefix + dot decimal (e.g. `"€7.55"`). Same `€X.XX` pattern as kevinshobbyshop.com. Strip `€` prefix, treat dot as decimal separator.
- **Stock logic**: UNKNOWN — no stock indicator on listing page. All products show identical `"Osta!"` button. Set `in_stock: null`.
- **Pagination**: url_pattern confirmed, 11 pages: `?page={page}` (absolute URL). 346 total products, 32/page.
- **Notes**: Custom ibutik Nordic platform. Works cleanly with requests+BS4. Note: category includes non-TCG items (board games, accessories) — may want name-based filtering for sealed TCG only.

---

### pbcards.fi
- **Status**: validated — 69 products across 6 pages ✅. Both stock states confirmed.
- **Price handling**: `p.price` text can contain old + current price concatenated via `\xa0` (e.g. `"€5,95\xa0€4,95"`). Old price also in `.old-price` span. Take the **last** price value. Prices use `€` prefix + comma decimal. Strip `€` prefix.
- **Stock logic**: CONTAINER CLASS — `li.product-card` gets `unavailable` class when out of stock. `unavailable` in container classes = OUT OF STOCK. Confirmed both states during validation. (Redundant: `.stock.overlay-valid` / `.stock.overlay-error` descendants also work, but container class is simpler.)
- **Pagination**: url_pattern confirmed, 6 pages: `?page={page}` (absolute URL)
- **Notes**: Shopify custom xtra theme. Works cleanly with requests+BS4.

---

### peliparatiisi.net
- **Status**: validated — 16 products, 1 page ✅
- **Price handling**: Use `.price-item--sale` (or `.price-item--regular` as fallback) — NOT `.price` full text (contains duplicated blob `"Regular price €5,90 EUR Regular price Sale price €5,90 EUR Unit price / per"`). Raw value: `"€5,90 EUR"`. Strip `€` prefix and `EUR` suffix, treat comma as decimal.
- **Stock logic**: INVERTED (badge text) — `.badge` with text `"Sold out"` = OUT OF STOCK. Confirmed during validation (~11 of 17 products out of stock). Check badge text exactly — same Dawn theme badge can hold other text (sale %, "New").
- **Pagination**: none (17 products, 1 page). Note: config says 17 products but prototype found 16 — minor discrepancy, 1 may have been added/removed.
- **Notes**: Shopify Dawn theme. Each `li.grid__item` contains `h3.card__heading` twice — use `h3.card__heading.h5 a` (with `.h5` class), not bare `h3.card__heading a`, to avoid duplicate name extraction. Works cleanly with requests+BS4.

---

### godofcards.com
- **Status**: validated — selectors work on page 1 ✅, full pagination not tested (24 pages, 775 products)
- **Price handling**: `sale-price` custom element text contains `"Sale price"` prefix (e.g. `"Sale price82,63€"`). Strip `"Sale price"` prefix text before extracting numeric value. Comma decimal, `€` suffix.
- **Stock logic**: UNKNOWN — no stock indicator on collection grid. `in_stock: null`.
- **Pagination**: url_pattern `?page={page}` works (absolute URL). 24 pages is an estimate — confirm actual last page at scrape time. Stop when page returns 0 products.
- **Notes**: Shopify with custom web-component theme (`<product-card>`, `<sale-price>` custom elements). BS4 parses custom elements as tags. Always scope to `.product-list product-card` to avoid nav-preview duplicate cards. Works cleanly with requests+BS4.

---

## Batch 7 — validated

### euroelite.fi
- **Status**: validated — 9 products, 1 page ✅. Both stock states confirmed.
- **Price handling**: Clean — `"60,67 €"` format.
- **Stock logic**: Normal — `.product-stock-balance-in-stock` present = in stock. `.product-stock-balance-out-of-stock` = out of stock. Both class names confirmed in DOM. All 9 products were in-stock during validation.
- **Pagination**: none (1 page confirmed)
- **Notes**: Finqu platform (same as korttistoppi.fi). Works cleanly with requests+BS4.

---

### pelimies.fi
- **Status**: validated — 41 products, 1 page ✅
- **Price handling**: Dot decimal, `€` suffix: `"49.90 €"`. Same pattern as spelexperten.fi — strip trailing `€`, treat dot as decimal.
- **Stock logic**: UNKNOWN — no stock class on container, no badge, no descendant stock element observed. Set `in_stock: null`.
- **Pagination**: none (41 products, 1 page)
- **Notes**: WooCommerce. Container `.product` has stray literal comma in class attribute (e.g. `"product tag-248, tag-478"`) — use base `.product` selector only. Works cleanly with requests+BS4.

---

### lelupartanen.fi
- **Status**: validated — 60 products, 1 page ✅ (63 claimed by page header, 3 not rendered)
- **Price handling**: `itemprop="Price"` attribute contains raw float `"16.95"` (no currency symbol, dot decimal). Append `€` and treat as EUR float. Do NOT use the formatted `<p>` text — it has no stable class.
- **Stock logic**: TEXT-BASED — plain `<p>` inside container contains `"Heti saatavilla"` (in stock) or `"Vain Jyväskylän myymälässä"` (store-only, treat as out-of-stock for online purposes). No CSS class available. Scrape the text and match known strings. Not confirmed for fully out-of-stock state.
- **Pagination**: none visible — 60 of 63 products render; 3 are inaccessible without a backing API. Accept this limit.
- **Notes**: React/MUI SPA — selectors use stable `itemprop` schema.org attributes, not hashed MUI class names. Works with requests+BS4 (server-side rendered).

---

### flea.fi
- **Status**: validated — 45 products across 5 pages ✅
- **Price handling**: `€` prefix + comma decimal: `"€54,99"`. Strip `€` prefix.
- **Stock logic**: UNKNOWN — no stock indicator observed. Set `in_stock: null`.
- **Pagination**: url_pattern relative — `"/collections/pokemon?page={page}"`. Prepend `https://www.flea.fi`. 5 pages × 9 products = 45 total confirmed.
- **Notes**: Shopify Turbo theme (`tt-` prefixed classes). Works cleanly with requests+BS4.

---

### muovijalelu.fi
- **Status**: validated — 47 products across 2 pages ✅. In-stock confirmed.
- **Price handling**: Clean — `"6,95 €"` format. Nested inside `<bdi>` inside `.woocommerce-Price-amount` — `get_text()` works fine.
- **Stock logic**: Normal — `p.stock.in-stock` present = in stock. Container also carries `instock`/`outofstock` class as fallback. Only in-stock products observed during validation.
- **Pagination**: url_pattern confirmed, 2 pages: `https://www.muovijalelu.fi/page/{page}/?s=pokemon&post_type=product`. Note: page 2 returned 12 products (not the 0 the config implied by `max_pages: 2` matching a 35-product set — actual total is 47).
- **Notes**: WooCommerce/Woodmart. Search results URL. Works cleanly with requests+BS4.

---

## Batch 8 — validated

### fantasialinna.com
- **Status**: validated — 62 products across 6 pages ✅
- **Price handling**: `.price .current` text is `"€49.90"` (€ prefix, dot decimal). Use `[itemprop="price"]` `content` attribute for a clean float (`"49.90"`) — more reliable than parsing the text. Treat as EUR.
- **Stock logic**: Normal — `.in-stock` present = in stock (`"Varastossa"` text). Out-of-stock variant class not confirmed (all products in-stock during validation).
- **Pagination**: url_pattern confirmed, 6 pages: `?page={page}` (absolute URL). 12/page × 5 + 2 = 62 total.
- **Notes**: CS-Cart platform. Works cleanly with requests+BS4.

---

### cdon.fi
- **Status**: BROKEN — JS-rendered React/Next.js app. Static HTML shows `"Ladataan tuotetta..."` placeholders only.
- **Price handling**: N/A
- **Stock logic**: N/A
- **Notes**: Large marketplace. 25 pages, ~48 products/page. **Requires Playwright.** Skip unless Playwright is added.

---

### muovitukku.fi
- **Status**: validated — 30 products, 1 page ✅. Both stock classes confirmed.
- **Price handling**: `"69,90€"` — no space before `€`. Comma decimal. Strip `€` suffix normally; space-stripping handles the no-space variant too.
- **Stock logic**: Normal — `.tuoteslideri-meta.is-green` present = in stock. `.tuoteslideri-meta.is-red` = out of stock (`"Ei saatavilla"`). Both confirmed during validation.
- **Pagination**: none (30 products, 1 page)
- **Notes**: WooCommerce + Elementor with custom `tuoteslideri` grid widget — use `.tuoteslideri-grid-item` as container, NOT standard `ul.products li.product`. Works cleanly with requests+BS4. Note: category mixes TCG with LEGO/MEGA Construx Pokemon sets — may want name-based filtering.

---

### hobbyhall.fi
- **Status**: BLOCKED — 403 regardless of User-Agent. Bot protection on all requests.
- **Price handling**: N/A
- **Stock logic**: N/A
- **Notes**: Nordic/Baltic PIGU Group retailer. Category mixes TCG with unrelated Pokemon merchandise (backpacks, bedding). **Skip this site** — blocked and low TCG relevance.

---

### pelikrypta.fi
- **Status**: validated — 2 products, 1 page ✅ (tiny catalog)
- **Price handling**: `"€7.00"` — `€` prefix, dot decimal. Strip `€` prefix.
- **Stock logic**: UNKNOWN — `.sold-out-message` span always carries `hidden` class in static HTML (Dawn theme toggles it via JS per-variant on interaction). Cannot detect stock from static page. Set `in_stock: null`.
- **Pagination**: none (2 products, 1 page — very sparse catalog)
- **Notes**: Shopify Dawn theme. Works with requests+BS4. Low value given only 2 products.

---

## Global scraper rules (applies to all sites)

1. **Price extraction**: Parse Finnish decimal format (comma as decimal separator, e.g. `"34,90 €"`). Variations seen: dot decimal (maxgaming.fi), `EUR` suffix (blockhousegames.net), `€` prefix (kevinshobbyshop.com), non-breaking space `\xa0` (swagykarp.fi, kerailykortti.fi). Normalise all to a plain float. Strip all non-numeric prefix text, strip `.visually-hidden` spans before reading price text. Take the last numeric value if multiple prices in one element. **Exception: karkkainen.com** — price lives in `data-ls-price` attribute (dot decimal float), not element text.
2. **Sale price extraction**: WooCommerce `span.price` may contain `<del>` (old) + `<ins>` (current). Extract `ins .woocommerce-Price-amount` when present, fall back to `.woocommerce-Price-amount`. Applies to kerailykortti.fi (confirmed), likely others.
3. **Suspicious prices**: Log a warning if extracted price < 2.00 € or > 2000 € — likely a placeholder or demo item (proshop.fi has a `"1 394 072,10 €"` demo product).
4. **Inverted stock sites**: casagrande.fi, porvoonpelikauppa.fi, korttistoppi.fi (badge text), pokepulls.fi (sold-out label), prisma.fi ("Ei saatavilla" text), karukortti.fi (sold-out label), spelparken.se ("Slutsåld" badge text), pelienmaa.com ("Loppuunmyyty" badge text), peliparatiisi.net ("Sold out" badge text) — absence of selector/text = in stock. Badge text must be checked exactly (same badge element can hold "Nyhet"/sale/percentage text).
5. **Container-class stock sites**: tcgkauppa.fi, muksumassi.fi, swagykarp.fi, kerailykortti.fi, kevinshobbyshop.com, pbcards.fi (`unavailable` class) — check container's own class list, not a child element.
6. **Attribute-based stock**: karkkainen.com — read `data-ls-availability` attribute (`"InStock"`/`"OutOfStock"`), not a CSS class or child element.
7. **Pagination page 1**: Never use the `{page}` pattern for page 1 — always use the base `source_url`.
8. **Offset pagination**: karkkainen.com uses `?offset={(page-1)*60}`, not `?page={page}`.
9. **Relative url_patterns**: blockhousegames.net, kevinshobbyshop.com, flea.fi use relative url_pattern strings — prepend base domain before requesting.
10. **Duplicate widget guard**: poromagia.com — use `article.product_line` only, ignore `article.product_pod`. prisma.fi — scope container to `ul[data-test-id='brand-product-list'] li` to avoid carousel duplicates.
11. **Broken sites (JS/blocked)**: vpd.fi, verkkokauppa.com (JS skeleton loaders), suomalainen.com (Algolia InstantSearch), konsolinet.fi (JS bot-check stub), cdon.fi (JS React placeholders) — need Playwright or skip. puolenkuunpelit.com (Cloudflare 403), hobbyhall.fi (403 bot protection), pokemoncenter.com (hCaptcha) — skip entirely.
12. **SEK prices**: spelparken.se prices are in Swedish krona (SEK), not EUR. Store currency alongside price, or convert at scrape time.
13. **Text-based stock**: lelupartanen.fi — no CSS class; match `"Heti saatavilla"` = in stock, `"Vain Jyväskylän myymälässä"` = online-unavailable.
14. **No-currency prices**: lelupartanen.fi `itemprop="Price"` returns a bare float (`"16.95"`) with no `€` — append EUR manually.
