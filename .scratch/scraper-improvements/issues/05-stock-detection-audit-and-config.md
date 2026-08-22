# 05 — Audit and configure stock detection for all active sites

**What to build:** 27 of 29 active sites have `latest_in_stock = NULL` for every listing, so back-in-stock events never fire for the vast majority of the catalogue. 14 of these sites already have an `in_stock` selector written in the config but are missing the `stock_mode` field that tells `detect_stock` how to interpret it. The remaining 13 have neither. For each active site without a `stock_mode`, fetch a representative page (ideally one with a mix of in-stock and out-of-stock products), inspect the HTML, and determine the correct mode and selector. Then add `stock_mode` (and `in_stock` selector if missing) to every config where detection is possible from the listing page. Sites where stock status is only available on the individual product page should be noted as `"stock_mode": "unknown"` with a comment so the gap is explicit.

From the prior audit, the expected modes are:
- `normal` (presence = in stock): Poromagia, Fantasialinna, Muovi ja Lelu, PBCards, Proshop, TCG-kauppa, Elli Madelli, Casagrande, Blockhouse Games, MaxGaming, Muovitukku
- `inverted` (presence = out of stock): KaruKortti, Porvoon Pelikauppa
- `attribute` (data-ls-availability): Karkkainen.com

Each should be verified against live HTML before the config is updated.

**Blocked by:** None — can start immediately.

**Status:** done

- [ ] Every active site has an explicit `stock_mode` in its config (no site left with the field absent)
- [ ] Back-in-stock events fire in a test scrape for at least one site that previously had null stock
- [ ] Sites where listing-page stock detection is impossible are documented with `"stock_mode": "unknown"`
- [ ] `detect_stock` behaviour is unchanged for the two sites that already had a mode configured (Peliparatiisi, Spelparken)
