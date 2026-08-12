# 07 — Catalog scrape prompt

## Question

Write a reusable Copilot browser prompt (`copilot_prompts/scrape_catalog.md`) that scrapes the 8 Cardmarket category pages and outputs a JSON file of popularity-ordered products.

The prompt must:
- Navigate all 8 category pages (Boosters, Booster Boxes, Theme Decks, Trainer Kits, Tins, Box Sets, Elite Trainer Boxes, Blisters)
- Paginate up to 10 pages per category (30 products per page)
- Capture per product: `cardmarket_product_id` (from product URL), `name`, `category`, `popularity_rank` (1 = first result = most popular)
- Output: a single JSON file with one object per product
- Operator passes the captcha manually; the prompt handles all navigation and extraction

Designed to be re-run quarterly as new sets release.

**Status: CLOSED**

## Resolution

`copilot_prompts/scrape_catalog.md` written. Covers: captcha pause, all 8 category URLs with pagination via `&site=N`, per-product extraction (id from listing data attrs / JSON-LD, name, category, popularity_rank), JSON output to `catalog_scrape.json`, null-safe id handling, summary report.

Blocking: 08
Blocked by: nothing (can be drafted independently of ticket 06)
