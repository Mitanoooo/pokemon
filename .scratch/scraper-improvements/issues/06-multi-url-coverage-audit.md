# 06 — Multi-URL coverage audit: identify all category URLs per site

**What to build:** Many sites use a single category URL scoped to booster boxes, silently missing ETBs, tins, blisters, and collection boxes that live under separate category paths. This ticket is a research task: for each active site, browse the site and identify every category URL needed to cover all sealed Pokémon products. Document the findings as a table in `.scratch/scraper-improvements/multi-url-findings.md`.

Sites confirmed to have gaps based on the coverage audit (zero readings for entire product types):

| Site | Missing types |
|---|---|
| KaruKortti | ETBs, tins, blisters |
| Korttistoppi | ETBs, tins |
| Swagykarp | ETBs, tins |
| TCG-kauppa | ETBs, tins, blisters |
| Muksumassi | ETBs |
| Peliparatiisi | Near-zero coverage overall |
| Poromagia | ETBs |
| Spelparken | Zero coverage overall |
| Keräilykortti.fi | Zero coverage overall |

Also check: Pelimies, PokePulls, Proshop, Prisma.fi, and any other site that looks narrow.

The output of this ticket directly drives ticket 08 (adding the URLs to configs).

**Blocked by:** None — can start immediately.

**Status:** done

- [ ] Every active site is checked for coverage gaps
- [ ] `.scratch/scraper-improvements/multi-url-findings.md` lists, per site: current URL, missing product types, and the additional category URLs needed
- [ ] Sites with complete coverage are noted as such (not silently omitted)
