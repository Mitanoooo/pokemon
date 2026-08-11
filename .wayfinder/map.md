# Wayfinder Map — Normalisation Overhaul

## Destination

A fully SQLite-backed normalisation system where every scraped `raw_name` maps to either a specific `cardmarket_products` row (by `idProduct`) or is confirmed null. An LLM CLI script handles bulk mapping at high confidence; a Streamlit review page handles the rest. The old `products` / `product_aliases` / `categories` tables are gone.

## Notes

Stack: Python, SQLite, Streamlit, Claude API (already wired).  
Catalogue source: `cardmarket_catalogue.json` (5006 products, sealed Pokémon only).  
Consult `/domain-modeling` and `/grilling` skills when resolving tickets.

**Locked decisions:**
- Canonical identity = `cardmarket_products.idProduct` (integer FK, no invented names)
- Null-mapping is an explicit row in `name_mappings` (status = `null_mapped`)
- Confidence score stored for all LLM results; auto-commit threshold = 0.85
- `raw_name` alone is the mapping key (no site_id in PK)
- `products`, `product_aliases`, `categories` tables are dropped after migration
- `price_readings.product_id` and `thresholds.product_id` FK directly into `cardmarket_products`
- LLM prompt lives inline in the CLI script as a module-level constant
- Review UI: dropdown first option = "— Not a Pokémon product", then products grouped by category sorted by existing mapping count; save on select

## Open tickets (frontier → blocked)

None — all tickets resolved. Map complete.

## Decisions so far

- [01 — Schema migration](tickets/01-schema-migration.md) — `cardmarket_products` + `name_mappings` live; old `products`/`product_aliases`/`categories` dropped; migration run 2026-08-11
- [02 — Catalogue import](tickets/02-catalogue-import.md) — `scripts/import_catalogue.py`; 5006 rows loaded into `cardmarket_products` on 2026-08-11
- [03 — LLM mapping CLI script](tickets/03-llm-mapping-script.md) — `copilot_prompts/llm_normalise.md`; Claude Code prompt, not a script; batches of 50, 0.85 threshold, writes directly to `name_mappings`
- [04 — Review UI](tickets/04-review-ui.md) — `app/views/mappings.py` "Mapping Review" page; save-on-select, dropdown sorted by mapping count, backfills `price_readings.product_id`
- [05 — Run migration and initial LLM pass](tickets/05-migration-run.md) — all steps done 2026-08-11; 292 mapped / 279 null_mapped / 728 undecided; 588/2658 price_readings backfilled; script at `scripts/run_llm_mapping.py`

## Not yet specified

- Error handling / retry strategy for Claude API calls in the LLM script (batch size, rate limits)
- Whether the review UI needs pagination or infinite scroll once the queue is large

## Out of scope

- Automatic LLM pass on every scrape run (decided: manual CLI only)
- Per-site overrides for the same raw_name (decided: raw_name key is global)
