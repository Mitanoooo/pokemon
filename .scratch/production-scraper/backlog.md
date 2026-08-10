# Backlog

Known issues and deferred work that don't yet have a ticket.

---

## Operator tasks

### [#16] Run email setup script on server
`scripts/setup_email.py` is built and tested but has not been run on the production server. SSH in, run `venv/bin/python scripts/setup_email.py`, confirm the test email arrives, then verify `grep GMAIL /opt/pokemon/.env` shows real credentials. See `.scratch/production-scraper/issues/16-run-email-setup-on-server.md` for the full checklist.

### Run normalisation pass
The scraper has now produced a full set of readings post-deployment (1,286 rows from the first production run on 2026-08-10). Run the normalisation pipeline to map raw product names to canonical sealed-product identifiers. This should be done before the digest is enabled so the digest only surfaces normalised products.

### Multi-path site audit (agentic browser + Copilot)
Make a pass through every enabled site config using an agentic browser session to check whether the site has multiple relevant category paths that should each be scraped — e.g. separate pages for boosters, booster boxes, blisters, ETBs, tins, elite trainer boxes. Currently each config has a single `source_url`. Sites that split their sealed catalog across several category URLs need either multiple configs or a comma-separated URL list (depending on what the runner supports at that point). Use Copilot in agentic mode to navigate each site and note additional paths; update configs or create follow-up tickets from the findings.

---

## Code gaps

### Runner: no test for all-None-price page with further pages remaining

`runner.run_site` correctly continues paginating when a page returns only None-price products (the "empty page → stop" guard checks `if not products`, which is False when products were found but all had unparseable prices). This is the right behaviour but has no test covering it. Add a test: two pages, page 1 returns 2 products both with None price, page 2 returns 2 valid products → both pages fetched, valid readings written, `null_price_count = 2`.

---

## First production scraper run (2026-08-10)

Ran `venv/bin/python -m scraper` manually on the server for the first time. Result: 1,286 price readings written across the enabled sites. 5 sites errored with `fetch returned None` (likely blocking/anti-bot or transient network issues, not yet investigated) — needs a follow-up look before relying on their data:

- Blockhouse Games (page 2 fetch failed)
- God of Cards
- Kevin's Hobby Shop
- Poromagia
- Proshop

All other enabled sites returned products successfully (some with a handful of skipped no-parseable-price products, which is expected/handled behaviour).

---

## Disabled sites

| Site | Reason disabled | What's needed to re-enable |
|------|----------------|---------------------------|
| Pelien Maa (`pelienmaa.com`) | All selectors null — was blocked by corporate proxy on dev machine. **Confirmed reachable from Hetzner (HTTP 200, 2026-08-10).** | Run LLM selector analysis, then re-enable. **Priority: high — unblocked, ready to proceed.** |
| Puolenkuun Pelit (`puolenkuunpelit.com`) | All selectors null. **Tested from Hetzner (2026-08-10): still returns HTTP 403** (with both plain curl and the scraper's real User-Agent) — this is a WAF/anti-bot block, not just the dev machine's corporate proxy. | Needs investigation into the 403 (Cloudflare/WAF fingerprinting, IP reputation, or geo-block) before selector analysis is worth doing. Not a simple re-enable. |
| VPD Pelikauppa (`vpd.fi`) | Selectors look correct (Magento 2, high confidence). **Tested from Hetzner (2026-08-10): still returns HTTP 403** with the scraper's real User-Agent — same class of block as Puolenkuun Pelit. | Needs investigation into the 403 before enabling — selectors are ready but the site can't be fetched at all yet. |
| Konsolinet (`konsolinet.fi`) | Returns JS bot-check stub (Client Challenge) on plain fetch — requires Playwright. | Add Playwright fetch support to the runner, or route through a headless-browser service. |
| CDON (`cdon.fi`) | JS-rendered React app (lazy-load). Plain requests returns placeholder HTML. | Playwright or headless browser. 25 pages × ~48 products is a large catalog. |
| Suomalainen.com (`suomalainen.com`) | Algolia InstantSearch — product list only renders after JS. | Headless browser or call Algolia search API directly (likely simpler). |
| Verkkokauppa.com (`verkkokauppa.com`) | Hashed styled-components class names unstable across deploys. No in-stock signal. | Identify stable data attributes; add in-stock detection before enabling. |
| Hobby Hall (`hobbyhall.fi`) | Brand page mixes TCG + unrelated Pokemon merchandise. No stock signal. | Add a product-name filter to skip non-TCG items, or find a more targeted URL. |
| Pokémon Center (`pokemoncenter.com`) | Imperva/hCaptcha blocks every request. All selectors null. | Needs official API, residential proxy service, or manual checking. Not viable with plain scraper. |
| Spelexperten (`spelexperten.fi`) | ibutik platform, 346 mixed products, no sealed-only subcategory URL. | Dropped by operator (ticket 13). Could revisit if a sealed subcategory URL is found. |
| Euro Elite Cards (`euroelite.fi`) | Mixed content, only 9 products total. Low value. | Dropped by operator (ticket 13). |

---

## Security (shared Hetzner box)

### Add authentication to drafter's deploy hook
The sibling `drafter` project's `/opt/upload_server.py` (port 9000) has zero authentication and runs as root — anyone who can reach port 9000 on `65.21.178.63` can trigger it. The pokemon deploy hook (port 9001, `pokemon-deploy.service`) was built with an `X-Deploy-Token` bearer check as a reference pattern. Apply the same kind of token check to drafter's hook, or otherwise restrict access to it.

### Harden box-level security more broadly
There is no Hetzner Cloud Firewall resource on this project and host-level `ufw` is inactive — every port a service binds to is directly internet-facing with no network-layer filtering. Set up a Hetzner Cloud Firewall (or enable and configure `ufw`) restricting inbound access to only the ports that need to be public (80/443, and SSH from known IPs), and review what's currently listening (`ss -tlnp`) for anything that shouldn't be exposed.

### Rotate leaked credentials
Two secrets were pasted into chat/found in a git remote URL during the pokemon deployment session and are considered compromised even though they were authorized for one-off use:
- Hetzner Cloud API token (used for the rescue-mode bootstrap) — rotate in the Hetzner Console under Security → API Tokens.
- GitHub PAT(s) — one from the drafter deployment doc, one that was embedded directly in the pokemon repo's `origin` remote URL (now stripped from the URL, but the token itself is still live until revoked) — rotate/revoke at github.com/settings/tokens.
