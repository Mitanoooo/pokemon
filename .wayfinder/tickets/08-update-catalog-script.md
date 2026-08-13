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

**Status: CLOSED**

## Resolution

`scripts/update_catalog.py` written (commit `35cb9fb`). Takes the scrape JSON as a positional argument, SSHes to Hetzner (`~/.ssh/pokemon-hetzner`, `root@65.21.178.63`) and pipes the payload to an inline Python snippet run under `/opt/pokemon/venv/bin/python`.

Run: `python scripts/update_catalog.py catalog_scrape.json`

**Behaviour beyond the original spec:**
- Deduplicates by `cardmarket_product_id` before sending — lowest `popularity_rank` wins, since a product can appear in more than one scraped category
- Entries with a null `cardmarket_product_id` or `popularity_rank` are dropped and reported as "duplicates/nulls dropped"
- **Resets curation first**: `UPDATE cardmarket_products SET is_curated = 0, popularity_rank = NULL WHERE is_curated = 1` runs before applying the scrape, so a re-scrape produces a clean slate rather than accumulating stale curated rows. This is what makes it idempotent
- Whole update runs in one transaction; reports `matched` / `not_found`

Blocking: 09, 10, 12
Blocked by: 06 (schema columns must exist), 07 (scrape output must exist)
