# Site config summary — all 41 sites (batches 1–8, plus k-ruoka.fi)

Confidence counts: **21 high**, **16 medium**, **4 low**.

## Config fields the scraper reads

- `site_name`, `method`, `selectors`, `confidence`, `notes` — as in every config.
- `availability` — how to read a listing's state. Optional; a config without it
  reports as "not tracked" rather than as all-unknown. In a config that has this
  block, a page fetched from one of the site's `preorder_urls` reads `preorder`
  and skips the forms below. Otherwise
  the keys resolve in this order and the first hit wins: `text_map` (badge text to
  state, matched as a casefolded substring under `selector`), `presence`
  (`selector` plus `present` and `absent` states), `container_class_map` (the
  container's own classes), `attribute` (`name` plus a value `map`), then
  `default`. States are `in_stock`, `out_of_stock`, `preorder`, `unknown`.
- `source_url` — the single category page to scrape.
- `source_urls` — array form of the above, for sites that split products across
  several category pages. Every URL is paginated on its own and all of them
  report under one site identity (the first URL identifies the site row). Use
  one or the other, not both; `source_urls` wins if both are present.
- `preorder_urls` — array of the site's own preorder category pages, scraped like
  the normal ones but after them, and marked: every listing read there gets
  `listings.from_preorder_url = 1`, and state `preorder` as long as the config has
  an `availability` block at all (without one the site stays untracked and reads
  `unknown`, so the column is the only trace). Never used for site
  identity. Only add a URL whose contents are mostly Pokémon — nothing filters
  listings by name, so a shop-wide preorder page imports its other brands too.
  See `.scratch/tracker-refocus/preorder-urls.md` for the per-site audit.
- `decimal_separator` — `"dot"` or `"comma"` (default `"comma"`), how the site
  prints prices.
- `pagination.type` — `"none"`, `"url_pattern"`, or `"offset"`, plus
  `url_pattern`, `max_pages`, and (offset only) `page_size` (default 60).
- `disabled` / `disabled_reason` — skip the site in a run.

To write or fix an `availability` block, run the probe first — it prints the
site's badge text, container classes and `data-*` values next to the split the
current config produces:

```
python -m scraper.probe site_configs/tcgkauppa.fi.json [--url N] [--limit 5]
python -m scraper.probe site_configs/tcgkauppa.fi.json --html-file page.html
python -m scraper.probe --all      # one coverage line per site
```

## Availability coverage after ticket 18

Of the 29 enabled configs, 28 carry an `availability` block checked against live
HTML and 1 (`kevinshobbyshop.com`) carries an unchecked one because the shop
answers HTTP 403 to every request from here. `karkkainen.com` used to have no
block at all: its listing cards all report `OutOfStock` in Lipscore markup,
including items its own product pages call in stock. Since 2026-09-03 its
`source_url` is the facet-filtered brand page, which lists only what Kärkkäinen
itself stocks, so it reads `in_stock` by default with `absent_means` for the rest,
the same way prisma.fi does.
`probe --all` puts every configured site at 0% unknown.

Six sites are **tracked in-stock-only** — their listing pages never show a
sold-out product, so an all-in-stock split there says nothing about what has sold
out: `blockhousegames.net`, `ellimadelli.fi`, `godofcards.com`, `muksumassi.fi`,
`muovijalelu.fi`, `pelimies.fi`. The per-site evidence is in
`.scratch/tracker-refocus/availability-pass.md`.

## High confidence (21)

- casagrande.fi — Casagrande
- ellimadelli.fi — Elli Madelli
- poromagia.com — Poromagia
- tcgkauppa.fi — TCG-kauppa
- porvoonpelikauppa.fi — Porvoon Pelikauppa
- maxgaming.fi — MaxGaming
- muksumassi.fi — Muksumassi
- korttistoppi.fi — Korttistoppi
- vpd.fi — VPD Pelikauppa
- karukortti.fi — KaruKortti
- prisma.fi — Prisma.fi
- konsolinet.fi — Konsolinet
- proshop.fi — Proshop
- spelparken.se — Spelparken
- spelexperten.fi — Spelexperten
- pbcards.fi — PBCards
- peliparatiisi.net — Peliparatiisi
- euroelite.fi — Euro Elite Cards
- flea.fi — Flea Lelukauppa
- muovijalelu.fi — Muovi ja Lelu
- fantasialinna.com — Fantasialinna

## Medium confidence (16)

- blockhousegames.net — Blockhouse Games
- cdon.fi — CDON
- godofcards.com — God of Cards
- hobbyhall.fi — Hobby Hall
- karkkainen.com — Karkkainen.com verkkokauppa
- kerailykortti.fi — Keräilykortti.fi
- kevinshobbyshop.com — Kevin's Hobby Shop
- kodintavaratalo.fi — JR Kodintavaratalo
- lelupartanen.fi — Lelukauppa Partanen
- muovitukku.fi — Muovitukku
- pelikrypta.fi — Pelikrypta (Ikamaa)
- pelimies.fi — Pelimies
- pokepulls.fi — PokePulls
- suomalainen.com — Suomalainen.com
- swagykarp.fi — Swagykarp
- verkkokauppa.com — Verkkokauppa.com

## Low confidence (4)

- **k-ruoka.fi** — Cloudflare WAF answers 403 ("Pyyntö estetty (CF/WB)") to every path but /robots.txt, from this machine and from the server, and headless Chromium gets the same, so no HTML was ever read and the selectors are empty. The intended handling is recorded: the brand page lists only in-stock products, so `default: in_stock` plus `absent_means: out_of_stock`. Needs a browser fetch from an unblocked IP, and a pinned store, since K-Ruoka scopes prices per store.
- **pelienmaa.com** — Blocked by this machine's corporate network security proxy (categorized "games" and refused before any Shopify content was served); no selectors could be inferred, needs revisiting from an unfiltered network.
- **pokemoncenter.com** — Blocked by Imperva/Incapsula bot-protection with an hCaptcha "I am human" challenge on every request (plain fetch and real browser both hit it); no product HTML was ever reached, and solving the CAPTCHA was intentionally not attempted (would bypass an anti-bot control) — likely needs an official API or a dedicated anti-bot-aware scraping approach instead.
- **puolenkuunpelit.com** — Blocked before any page content loaded by the same corporate network security policy interstitial ("games" category); no product HTML served, needs revisiting from an unfiltered network.
