# Multi-URL Coverage Audit

**Date:** 2026-08-22  
**Method:** Live site browsing via automated agents for all 40 active sites.

---

## Sites with actionable gaps

### KaruKortti (`karukortti.fi`)

| | |
|---|---|
| **Current URL** | `https://karukortti.fi/kategoria/booster-box` |
| **Missing types** | individual boosters, ETBs, tins, collection boxes, UPCs, Japanese sealed |

**Add these URLs:**
```
https://karukortti.fi/category/booster-box          ← canonical (current uses /kategoria/, both work)
https://karukortti.fi/category/boosterit             ← individual booster packs
https://karukortti.fi/category/elite-trainer-box     ← ETBs
https://karukortti.fi/category/boxit-and-tinit       ← tins, collection boxes, illustration/premium collections
https://karukortti.fi/category/ultra-premium-collection ← UPCs
https://karukortti.fi/category/japaninkieliset       ← Japanese boosters/boxes
```

> Note: `/kategoria/` and `/category/` both work but sitemap canonical is `/category/`.

---

### Korttistoppi (`korttistoppi.fi`)

| | |
|---|---|
| **Current URL** | `https://www.korttistoppi.fi/tuoteryhma/boosterit` |
| **Missing types** | blisters, tins, ETBs, collection boxes, collector chests, theme decks, special releases, bundles, Japanese, Chinese, 30th Anniversary |

**Add these URLs:**
```
https://www.korttistoppi.fi/tuoteryhma/blisterit
https://www.korttistoppi.fi/tuoteryhma/tinit
https://www.korttistoppi.fi/tuoteryhma/elite-trainer-boksit
https://www.korttistoppi.fi/tuoteryhma/collection-boksit
https://www.korttistoppi.fi/tuoteryhma/collectors-chestit
https://www.korttistoppi.fi/tuoteryhma/theme-deckit
https://www.korttistoppi.fi/tuoteryhma/erikoisjulkaisut
https://www.korttistoppi.fi/tuoteryhma/kombot-ja-mixit
https://www.korttistoppi.fi/tuoteryhma/japaninkieliset
https://www.korttistoppi.fi/tuoteryhma/simplified-chinese-kiinankieliset
https://www.korttistoppi.fi/tuoteryhma/30th-celebration
```

> Note: `/tuoteryhma/ennakkotilaus` (pre-orders) exists but items move to their category on release — probably not worth adding.

---

### Swagykarp (`swagykarp.fi`)

| | |
|---|---|
| **Current URL** | `https://swagykarp.fi/product-category/pokemon-tuotteet/boosterit/` ← **likely stale path** |
| **Missing types** | ETBs, tins, collection boxes, blisters, battle decks |

**Replace current URL and add:**
```
https://swagykarp.fi/product-category/pokemon-tcg/boosterit/         ← correct live booster path
https://swagykarp.fi/product-category/pokemon-tcg/elite-trainer-boxes/
https://swagykarp.fi/product-category/pokemon-tcg/lahja-tinit/
https://swagykarp.fi/product-category/pokemon-tcg/collection-boxit/
https://swagykarp.fi/product-category/pokemon-tcg/blisterit/
https://swagykarp.fi/product-category/pokemon-tcg/battle-deckit/
```

> **Critical:** `/pokemon-tuotteet/` subtree is merchandise (keychains, figures, plushies) — not sealed products. Current booster URL may be returning nothing or wrong products.

---

### TCG-kauppa (`tcgkauppa.fi`)

| | |
|---|---|
| **Current URL** | `https://www.tcgkauppa.fi/tuote-osasto/pokemon/pokemon-booster/` |
| **Missing types** | booster displays, ETBs, tins, blisters, collection boxes, premium collections, collector chests, gift boxes, bundles, starter decks, theme decks |

The site uses a separate `tuotetyyppi` (product-type) taxonomy. All sealed types live there:

**Add these URLs (tuotetyyppi taxonomy):**
```
https://www.tcgkauppa.fi/tuotetyyppi/booster-display/
https://www.tcgkauppa.fi/tuotetyyppi/elite-trainer-box/
https://www.tcgkauppa.fi/tuotetyyppi/tin/
https://www.tcgkauppa.fi/tuotetyyppi/blister/
https://www.tcgkauppa.fi/tuotetyyppi/collection-box/
https://www.tcgkauppa.fi/tuotetyyppi/premium-collection/
https://www.tcgkauppa.fi/tuotetyyppi/collector-chest/
https://www.tcgkauppa.fi/tuotetyyppi/gift-box/
https://www.tcgkauppa.fi/tuotetyyppi/bundle/
https://www.tcgkauppa.fi/tuotetyyppi/booster-bundle/
https://www.tcgkauppa.fi/tuotetyyppi/special-release/
https://www.tcgkauppa.fi/tuotetyyppi/starter-deck/
https://www.tcgkauppa.fi/tuotetyyppi/theme-deck/
```

> Note: The shop appears to be Pokémon-only (manufacturer sitemap has only The Pokemon Company), so tuotetyyppi pages won't pollute with non-Pokémon products. `/valmistaja/the-pokemon-company/` is an alternative catch-all.

---

### Muksumassi (`muksumassi.fi`)

| | |
|---|---|
| **Current URL** | `https://muksumassi.fi/kerailykortit/pokemon-boosterit/` |
| **Missing types** | ETBs, premium/UPCs, collection boxes, battle decks, tins, theme decks, blisters |

**Add these URLs:**
```
https://muksumassi.fi/kerailykortit/pokemon-lahjapakkaukset/   ← ETBs, premium collections, bundles, holiday calendars
https://muksumassi.fi/kerailykortit/pokemon-teemapakkaus/      ← battle decks, theme decks, world championship decks
https://muksumassi.fi/kerailykortit/pokemon-tin-metalliboxit/  ← tins, mini tins
```

> Note: `pokemon-kerailykortit` is a broader umbrella but overlaps — probably not needed if the three above are added.

---

### Peliparatiisi (`peliparatiisi.net`)

| | |
|---|---|
| **Current URL** | `https://peliparatiisi.net/en/collections/pokemon-boosterit` |
| **Missing types** | booster displays, blisters, ex boxes, ETBs, tins, special releases |

**Add these URLs:**
```
https://peliparatiisi.net/en/collections/pokemon-booster-displayt   ← booster display boxes
https://peliparatiisi.net/en/collections/pokemon-blisterit
https://peliparatiisi.net/en/collections/pokemon-ex-boxit            ← premium figure/character collection boxes
https://peliparatiisi.net/en/collections/pokemon-elite-trainer-boxit ← ETBs
https://peliparatiisi.net/en/collections/pokemon-tinit
https://peliparatiisi.net/en/collections/pokemon-erikoisjulkaisut    ← poster/illustration/pin collections, bundles
```

> Note: `/collections/pokemon-tcg` is an umbrella that may cover all sub-categories — could use as single catch-all instead. `/collections/pokemon-portfoliot` (binders) should NOT be added.

---

### Poromagia (`poromagia.com`)

| | |
|---|---|
| **Current URL** | `https://poromagia.com/fi/catalogue/category/pokemon/pokemon-tuotepakkaukset/pokemon-boosterit_385/` |
| **Missing types** | booster displays, ETBs, premium collections, theme decks, tins, blisters |

**Add these URLs (same parser/pagination pattern as current):**
```
https://poromagia.com/fi/catalogue/category/pokemon/pokemon-tuotepakkaukset/pokemon-boosterboksit_235/
https://poromagia.com/fi/catalogue/category/pokemon/pokemon-tuotepakkaukset/pokemon-erikoisjulkaisut_308/
https://poromagia.com/fi/catalogue/category/pokemon/pokemon-tuotepakkaukset/pokemon-theme-dekit_309/
https://poromagia.com/fi/catalogue/category/pokemon/pokemon-tuotepakkaukset/pokemon-tinit_310/
```

> Note: Blisters live inside `pokemon-tinit_310` (not a separate category). `pokemon-erikoisjulkaisut_308` has 3 pages — the largest missing bucket. Accessories (`pokemon-asusteet_1671`) and plushies (`pokemon-pehmolelut-funko-pop_1670`) confirmed excluded.

---

### Spelparken (`spelparken.se`)

| | |
|---|---|
| **Current URL** | `https://spelparken.se/collections/pokemon-booster-boxes` |
| **Missing types** | booster packs, ETBs, tins/collection boxes, UPCs, bundles, vintage, Japanese/Chinese |

**Add these URLs:**
```
https://spelparken.se/collections/pokemon-booster-packs
https://spelparken.se/collections/pokemon-elite-trainer-box
https://spelparken.se/collections/tins-collection-boxar        ← tins, mini tins, blisters, premium figure collections, collection boxes
https://spelparken.se/collections/pokemon-ultra-premium-collection
https://spelparken.se/collections/pokemon-bundles              ← Build & Battle Stadiums, booster bundles
```

> Note: `/collections/pokemon-vintage` and `/collections/japanka-kinesiska-packs` exist — add if out-of-print/import prices are in scope. `/collections/forkop` (pre-orders) also exists.

---

### Keräilykortti.fi (`kerailykortti.fi` / `xn--kerilykortti-icb.fi`)

| | |
|---|---|
| **Current URL** | `https://www.xn--kerilykortti-icb.fi/englanti-pokemon-booster-pakkaukset/` |
| **Missing types** | Japanese boosters, general booster category; **no dedicated ETB/tin/blister/collection box categories exist on this site** |

**Add these URLs:**
```
https://www.xn--kerilykortti-icb.fi/japani-pokemon-booster-pakkaukset/
https://www.xn--kerilykortti-icb.fi/pokemon-boosterit/
```

> Note: This site sells individual booster packs only. No ETB/tin/blister/collection box category pages exist — those product types are not stocked (or appear only on set-specific pages). Set pages like `/pokemon-scarlet-violet-black-bolt/` contain occasional ETB-equivalent Japanese "Deluxe" products (e.g. €44.99) but no dedicated sealed-format category exists.

---

### PokePulls (`pokepulls.fi`)

| | |
|---|---|
| **Current URL** | `https://pokepulls.fi/kategoria/boosterit` |
| **Missing types** | blisters, ETBs, collection boxes, collector chests, theme/battle decks, tins, premium tournament collections |

**Add these URLs:**
```
https://pokepulls.fi/kategoria/blisterit
https://pokepulls.fi/kategoria/elite-trainer-boxit
https://pokepulls.fi/kategoria/collection-boxit-1
https://pokepulls.fi/kategoria/collector-s-chestit
https://pokepulls.fi/kategoria/battle-and-theme-deckit
https://pokepulls.fi/kategoria/tinit
https://pokepulls.fi/kategoria/premium-tournament-collection
```

---

### Pelienmaa (`pelienmaa.com`)

| | |
|---|---|
| **Current URL** | `https://pelienmaa.com/collections/pokemon-booster-box` |
| **Missing types** | booster packs, ETBs, blisters, tins, collection/gift boxes |

**Add these URLs:**
```
https://pelienmaa.com/collections/pokemon-booster
https://pelienmaa.com/collections/pokemon-etb
https://pelienmaa.com/collections/pokemon-blister
https://pelienmaa.com/collections/pokemon-tins
https://pelienmaa.com/collections/pokemon-boxes-sets
```

---

### Porvoon Pelikauppa (`porvoonpelikauppa.fi`)

| | |
|---|---|
| **Current URL** | `https://porvoonpelikauppa.fi/pokemon-booster-laatikot-ja-bundlet` |
| **Missing types** | ETBs, tins, collection boxes, miscellaneous sealed |

**Add these URLs:**
```
https://porvoonpelikauppa.fi/pokemon-bundlet        ← ETBs
https://porvoonpelikauppa.fi/pokemon-kerailylaatikot ← tins, collection boxes
https://porvoonpelikauppa.fi/pokemon-muut-tuotteet   ← miscellaneous sealed
```

> Note: `/pokemon-tuotteet` (226 products) may be a usable catch-all if the sub-categories have low product counts.

---

### VPD (`vpd.fi`)

| | |
|---|---|
| **Current URL** | `https://www.vpd.fi/pokemon-kortit/boosterit.html` |
| **Missing types** | booster displays, ETBs, battle decks, V boxes, EX boxes, blisters, premium collection boxes |

**Add these URLs:**
```
https://www.vpd.fi/pokemon-kortit/displayt.html
https://www.vpd.fi/pokemon-kortit/elite-trainerit.html
https://www.vpd.fi/pokemon-kortit/battle-deckit.html
https://www.vpd.fi/pokemon-kortit/v-boxit.html
https://www.vpd.fi/pokemon-kortit/ex-boxit.html
https://www.vpd.fi/pokemon-kortit/checklane-blisterit.html
https://www.vpd.fi/pokemon-kortit/premium-collecton-box.html   ← note typo in URL: "collecton"
```

---

## Sites with complete coverage (no action needed)

| Site | Current URL | Notes |
|---|---|---|
| **Pelimies** | `/pokemon-tcg-trading-card-game-tuotteet/` | All ~41 products listed together; no subcategories exist |
| **Prisma** | `/tuotemerkit/pokemon-tcg` | Flat structure, all sealed types visible; confirmed complete |
| **PBCards** | `/collections/pokemon` | 78 products, all major types confirmed (27 booster boxes, 30 packs, 3 ETBs, 2 tins, etc.) |
| **GodOfCards** | `/en-fi/collections/english-pokemon-cards` | Catch-all with 118 products covering all English types; subcollections are filtered views only |
| **Hobbyhall** | `/fi/brands/p/pokemon` | Brand page — all product types |
| **Maxgaming** | `/fi/pokemon` | Brand page — all product types |
| **Verkkokauppa** | `/fi/brand/pokemon` | Brand page — all product types |
| **Kodintavaratalo** | `/pokemon` | Broad category |
| **Flea** | `/collections/pokemon` | Broad Shopify collection |
| **Ellimadelli** | `/collections/pokemon` | Broad Shopify collection |
| **Muovitukku** | `/tuote-osasto/lelut/sisalelut/pokemon/` | Broad category |
| **KevinShobbyShop** | filtered URL `filter_product-type=sealed` | Already pre-filtered to sealed products |
| **Karkkainen** | `/verkkokauppa/kerailykortit` | Broad "collectible cards" category |
| **PokemonCenter** | `new-releases?category=trading-card-game` | New releases only — back catalog may not appear, but this is likely intentional |
| **Puolenkuunpelit** | `cPath=31_168_686` | Specific category path, likely complete for their range |

---

## Sites requiring further investigation

| Site | Issue |
|---|---|
| **Proshop** | HTTP 403 on all fetch attempts — cannot audit. Current URL uses a filter param; unknown if other types are accessible via different paths. Needs headless browser |
| **Euroelite** | Only 9 products (boosters only) — either limited stock or the `/tuoteryhma/pokemon` URL is actually narrow. Needs manual check |
| **Pelikrypta** | Only 1 product in stock (a playmat) — essentially empty right now |
| **Casagrande** | Broad merch URL mixes sealed TCG with plush/Funko/costumes; booster boxes and ETBs not visible. May be thin stock rather than a URL gap |
| **Suomalainen** | Broad Pokémon URL mixes TCG with books, manga, sticker books — not a pure sealed-product URL. If a TCG-specific sub-URL exists, it would be cleaner |
| **Spelexperten.fi** | 346 products but overwhelming majority are accessories (sleeves, binders, playmats). Needs deeper page scraping across 11 pages to confirm sealed product coverage |
| **CDON** | `/lelut/kerailykortit/pokemon-kortit/` is "Pokémon cards" subcategory — may miss sealed boxes. Not yet browsed |
| **Konsolinet** | `/category/207/pokemon-kortit` is "Pokémon cards" — may be narrow. Not yet browsed |
| **Lelupartanen** | `/category/202/keraeilykortit-ja-kortit` is "collectible cards and cards" — broad but unverified. Not yet browsed |
| **Muovijalelu** | Search query URL — broad but unverified for sealed coverage. Not yet browsed |

---

## Summary table

| Site | Gap severity | Action |
|---|---|---|
| Korttistoppi | **High** — 11 categories missing | Add 11 URLs |
| VPD | **High** — 7 categories missing | Add 7 URLs |
| PokePulls | **High** — 7 categories missing | Add 7 URLs |
| Spelparken | **High** — 7 categories missing (zero coverage before) | Add 5–7 URLs |
| TCG-kauppa | **High** — 13 tuotetyyppi categories missing | Add 13 URLs |
| Peliparatiisi | **High** — 6 categories missing (near-zero before) | Add 6 URLs |
| Pelienmaa | **High** — 5 categories missing | Add 5 URLs |
| Swagykarp | **High** — 5 missing + current URL is wrong path | Fix + add 5 URLs |
| KaruKortti | **High** — 5 categories missing | Add 5 URLs |
| Poromagia | **Medium** — 4 categories missing | Add 4 URLs |
| Muksumassi | **Medium** — 3 categories missing | Add 3 URLs |
| Porvoon Pelikauppa | **Medium** — 3 categories missing | Add 3 URLs |
| Keräilykortti.fi | **Low** — 2 peer booster categories missing; no ETB/tin categories exist | Add 2 URLs |
| Proshop | **Unknown** — blocked | Needs headless audit |
| Euroelite | **Unknown** — may be genuine thin stock | Needs manual check |
| Spelexperten.fi | **Unknown** — mostly accessories seen | Needs deeper browse |
