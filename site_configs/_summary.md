# Site config summary — all 40 sites (batches 1–8)

Confidence counts: **21 high**, **16 medium**, **3 low**.

## Config fields the scraper reads

- `site_name`, `method`, `selectors`, `confidence`, `notes` — as in every config.
- `availability` — how to read a listing's state. Optional; a config without it
  reports as "not tracked" rather than as all-unknown. Keys, resolved in this
  order and first hit wins: `text_map` (badge text to state, matched as a
  casefolded substring under `selector`), `presence` (`selector` plus `present`
  and `absent` states), `container_class_map` (the container's own classes),
  `attribute` (`name` plus a value `map`), then a preorder-URL fallback, then
  `default`. States are `in_stock`, `out_of_stock`, `preorder`, `unknown`.
- `source_url` — the single category page to scrape.
- `source_urls` — array form of the above, for sites that split products across
  several category pages. Every URL is paginated on its own and all of them
  report under one site identity (the first URL identifies the site row). Use
  one or the other, not both; `source_urls` wins if both are present.
- `decimal_separator` — `"dot"` or `"comma"` (default `"comma"`), how the site
  prints prices.
- `pagination.type` — `"none"`, `"url_pattern"`, or `"offset"`, plus
  `url_pattern`, `max_pages`, and (offset only) `page_size` (default 60).
- `disabled` / `disabled_reason` — skip the site in a run.

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

## Low confidence (3)

- **pelienmaa.com** — Blocked by this machine's corporate network security proxy (categorized "games" and refused before any Shopify content was served); no selectors could be inferred, needs revisiting from an unfiltered network.
- **pokemoncenter.com** — Blocked by Imperva/Incapsula bot-protection with an hCaptcha "I am human" challenge on every request (plain fetch and real browser both hit it); no product HTML was ever reached, and solving the CAPTCHA was intentionally not attempted (would bypass an anti-bot control) — likely needs an official API or a dedicated anti-bot-aware scraping approach instead.
- **puolenkuunpelit.com** — Blocked before any page content loaded by the same corporate network security policy interstitial ("games" category); no product HTML served, needs revisiting from an unfiltered network.
