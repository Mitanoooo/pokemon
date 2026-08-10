# Backlog

Known issues and deferred work that don't yet have a ticket.

---

## Operator tasks

### [#16] Run email setup script on server
`scripts/setup_email.py` is built and tested but has not been run on the production server. SSH in, run `venv/bin/python scripts/setup_email.py`, confirm the test email arrives, then verify `grep GMAIL /opt/pokemon/.env` shows real credentials. See `.scratch/production-scraper/issues/16-run-email-setup-on-server.md` for the full checklist.

### Run normalisation pass
Once the scraper has produced a full set of readings post-deployment, run the normalisation pipeline to map raw product names to canonical sealed-product identifiers. This should be done before the digest is enabled so the digest only surfaces normalised products.

### Multi-path site audit (agentic browser + Copilot)
Make a pass through every enabled site config using an agentic browser session to check whether the site has multiple relevant category paths that should each be scraped — e.g. separate pages for boosters, booster boxes, blisters, ETBs, tins, elite trainer boxes. Currently each config has a single `source_url`. Sites that split their sealed catalog across several category URLs need either multiple configs or a comma-separated URL list (depending on what the runner supports at that point). Use Copilot in agentic mode to navigate each site and note additional paths; update configs or create follow-up tickets from the findings.

---

## Code gaps

### Runner: no test for all-None-price page with further pages remaining

`runner.run_site` correctly continues paginating when a page returns only None-price products (the "empty page → stop" guard checks `if not products`, which is False when products were found but all had unparseable prices). This is the right behaviour but has no test covering it. Add a test: two pages, page 1 returns 2 products both with None price, page 2 returns 2 valid products → both pages fetched, valid readings written, `null_price_count = 2`.

---

## Disabled sites

| Site | Reason disabled | What's needed to re-enable |
|------|----------------|---------------------------|
| Pelien Maa (`pelienmaa.com`) | All selectors null — site blocked by corporate proxy on dev machine. | Verify reachability from Hetzner after deployment. If reachable, run LLM selector analysis. **Priority: high** (likely reachable from Hetzner). |
| Puolenkuun Pelit (`puolenkuunpelit.com`) | All selectors null — same corporate proxy block (Tietoturvailmoitus, "games" category). | Same as Pelien Maa: verify from Hetzner, then run selector analysis. **Priority: high**. |
| VPD Pelikauppa (`vpd.fi`) | Selectors look correct (Magento 2, high confidence) but never verified from a non-proxy network. | Verify reachability from Hetzner and do a test run. Lowest-effort re-enable candidate. **Priority: high**. |
| Konsolinet (`konsolinet.fi`) | Returns JS bot-check stub (Client Challenge) on plain fetch — requires Playwright. | Add Playwright fetch support to the runner, or route through a headless-browser service. |
| CDON (`cdon.fi`) | JS-rendered React app (lazy-load). Plain requests returns placeholder HTML. | Playwright or headless browser. 25 pages × ~48 products is a large catalog. |
| Suomalainen.com (`suomalainen.com`) | Algolia InstantSearch — product list only renders after JS. | Headless browser or call Algolia search API directly (likely simpler). |
| Verkkokauppa.com (`verkkokauppa.com`) | Hashed styled-components class names unstable across deploys. No in-stock signal. | Identify stable data attributes; add in-stock detection before enabling. |
| Hobby Hall (`hobbyhall.fi`) | Brand page mixes TCG + unrelated Pokemon merchandise. No stock signal. | Add a product-name filter to skip non-TCG items, or find a more targeted URL. |
| Pokémon Center (`pokemoncenter.com`) | Imperva/hCaptcha blocks every request. All selectors null. | Needs official API, residential proxy service, or manual checking. Not viable with plain scraper. |
| Spelexperten (`spelexperten.fi`) | ibutik platform, 346 mixed products, no sealed-only subcategory URL. | Dropped by operator (ticket 13). Could revisit if a sealed subcategory URL is found. |
| Euro Elite Cards (`euroelite.fi`) | Mixed content, only 9 products total. Low value. | Dropped by operator (ticket 13). |
