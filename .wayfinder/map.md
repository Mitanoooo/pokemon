# Wayfinder Map — Normalisation Overhaul

## Destination

A fully SQLite-backed normalisation system where every scraped `raw_name` maps to either a specific `cardmarket_products` row (by `idProduct`) or is confirmed null. An LLM CLI script handles bulk mapping at high confidence; a Streamlit review page handles the rest. The old `products` / `product_aliases` / `categories` tables are gone.

## Notes

Stack: Python, SQLite, Streamlit, Claude API (already wired).  
Catalogue source: `cardmarket_catalogue.json` (5006 products, sealed Pokémon only).  
Consult `/domain-modeling` and `/grilling` skills when resolving tickets.

**Locked decisions (initial overhaul):**
- Canonical identity = `cardmarket_products.idProduct` (integer FK, no invented names)
- Null-mapping is an explicit row in `name_mappings` (status = `null_mapped`)
- Confidence score stored for all LLM results; auto-commit threshold = 0.85
- `raw_name` alone is the mapping key (no site_id in PK)
- `products`, `product_aliases`, `categories` tables are dropped after migration
- `price_readings.product_id` and `thresholds.product_id` FK directly into `cardmarket_products`
- LLM prompt lives inline in the CLI script as a module-level constant
- Review UI: dropdown first option = "— Not a Pokémon product", then products grouped by category sorted by existing mapping count; save on select

**Locked decisions (accuracy overhaul — see [spec](spec-accuracy-overhaul.md)):**
- Ground truth catalog = curated subset of `cardmarket_products` marked `is_curated = 1`, ordered by `popularity_rank`
- Catalog sourced from 8 Cardmarket category pages (popularity-ordered); re-scraped manually, quarterly
- Classification rule: include if product belongs to one of the 8 curated categories; `null_mapped` everything else
- Normalization uses few-shot calibration examples (25 products, human-annotated) as prompt context
- Shadow mode: new mappings accumulate locally; production `name_mappings` wiped and replaced atomically at finalization
- `undecided` reserved for genuinely unrecognizable raw_names only; not a substitute for low LLM confidence
- No automated tests; operator reviews each batch CSV before committing

## Open tickets (frontier → blocked)

- [12 — Run the accuracy pipeline](tickets/12-run-accuracy-pipeline.md) — end-to-end execution *(frontier — steps 1–2 done 2026-08-13; step 3 calibration is next and needs an operator)*

Every artefact ticket (01–11) is closed. Ticket 12 is pure execution and cannot be fully automated: step 1 requires an operator to pass the Cardmarket captcha in a Copilot browser session, and steps 3–4 are interactive by design (calibration answers, per-batch CSV review).

The 2026-08-13 scrape landed as 8 `catalog_<category>.txt` dumps with no product ids rather than `catalog_scrape.json`, so `scripts/extract_catalog.py` was added to recover ids by slug-folding against `cardmarket_catalogue.json` (1,942 / 1,960 resolved). Catalog curation is now live on Hetzner: 1,942 rows at `is_curated=1`.

## Decisions so far

- [01 — Schema migration](tickets/01-schema-migration.md) — `cardmarket_products` + `name_mappings` live; old `products`/`product_aliases`/`categories` dropped; migration run 2026-08-11
- [02 — Catalogue import](tickets/02-catalogue-import.md) — 5006 rows loaded into `cardmarket_products` on 2026-08-11 (script `scripts/import_catalogue.py` since deleted in `abd02dd`; the data load is done, re-import would need it restored from git history)
- [03 — LLM mapping CLI script](tickets/03-llm-mapping-script.md) — `copilot_prompts/llm_normalise.md`; Claude Code prompt, not a script; batches of 50, 0.85 threshold, writes directly to `name_mappings`
- [04 — Review UI](tickets/04-review-ui.md) — `app/views/mappings.py` "Mapping Review" page; save-on-select, dropdown sorted by mapping count, backfills `price_readings.product_id`
- [05 — Run migration and initial LLM pass](tickets/05-migration-run.md) — all steps done 2026-08-11; 292 mapped / 279 null_mapped / 728 undecided; 588/2658 price_readings backfilled (script `scripts/run_llm_mapping.py` since deleted in `abd02dd`; superseded by the ticket-10 prompt, and this whole result is about to be replaced by the ticket-12 finalize)
- [06 — Schema: curated catalog columns](tickets/06-schema-curated-catalog.md) — `is_curated` + `popularity_rank` added to `cardmarket_products` on Hetzner 2026-08-12; `schema.sql` matches
- [07 — Catalog scrape prompt](tickets/07-catalog-scrape-prompt.md) — `copilot_prompts/scrape_catalog.md`; 8 category URLs, `&site=N` pagination to 10 pages, listing-pages-only, outputs `catalog_scrape.json`
- [08 — update_catalog.py](tickets/08-update-catalog-script.md) — `scripts/update_catalog.py`; dedupes by product id (lowest rank wins), resets all curation before applying so re-scrapes are idempotent
- [09 — Calibration session prompt](tickets/09-calibration-prompt.md) — `copilot_prompts/llm_calibrate.md`; 25 stratified raw_names, difflib top-5 candidates, blocks on operator input per item, writes `calibration_examples.md`
- [10 — Batch normalization prompt](tickets/10-batch-normalise-prompt.md) — `copilot_prompts/llm_batch_normalise.md`; supersedes `llm_normalise.md`; batches of 100, diffs against `draft_mappings.json`, pauses per batch
- [11 — apply_batch.py](tickets/11-apply-batch-script.md) — `scripts/apply_batch.py`; accumulate to `draft_mappings.json`, `--finalize` does DELETE+INSERT+backfill in one transaction on Hetzner

## Not yet specified

- Error handling / retry strategy for Claude API calls in the LLM script (batch size, rate limits)
- Whether the review UI needs pagination or infinite scroll once the queue is large

## Out of scope

- Automatic LLM pass on every scrape run (decided: manual CLI only)
- Per-site overrides for the same raw_name (decided: raw_name key is global)
