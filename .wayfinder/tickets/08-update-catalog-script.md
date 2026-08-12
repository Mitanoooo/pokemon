# 08 — update_catalog.py

## Question

Write a script (`scripts/update_catalog.py`) that reads the scrape output from ticket 07 and applies it to the Hetzner DB.

The script must:
- Accept the scrape output JSON file as input
- SSH into the Hetzner server (same pattern as `llm_normalise.md`)
- For each entry: match by `cardmarket_product_id` (exact integer), set `is_curated = 1` and `popularity_rank`
- Leave rows not present in the scrape output unchanged (`is_curated` stays 0)
- Report: matched count, not-found count (products in scrape file but absent from DB)
- Be idempotent: safe to re-run after a fresh scrape

**Status: OPEN**

Blocking: 09, 10, 12
Blocked by: 06 (schema columns must exist), 07 (scrape output must exist)
