# Spec — Normalization Accuracy Overhaul

## Problem Statement

The normalization system built in the initial overhaul has a 56% undecided rate: 728 of 1,296 distinct `raw_name` values in `name_mappings` are `status='undecided'`, meaning most `price_readings` rows have no `product_id` and the price tracker is largely non-functional. The root causes are: (1) the ground truth catalog is all 5,006 Cardmarket products sorted alphabetically — too broad and with no relevance signal; (2) the LLM has no examples to learn from; (3) there is no signal about which products are actually stocked in Finland, so the LLM can't prefer plausible matches over obscure ones.

## Solution

Replace the normalization ground truth with a curated, popularity-ordered catalog scraped from the 8 Cardmarket category pages. Build a human-in-the-loop calibration session to generate annotated matching examples. Use those examples plus popularity ordering in a new, improved batch normalization prompt. Accumulate all verified batch outputs locally in shadow mode, then atomically swap the full new mapping set into production once every batch is verified.

## User Stories

1. As the operator, I want to run a reusable Copilot browser prompt that scrapes the 8 Cardmarket category pages and outputs a popularity-ordered catalog file, so that the normalization ground truth reflects what is actually available and popular on Cardmarket.
2. As the operator, I want the scrape prompt to be re-runnable periodically, so that the catalog stays current as new Pokémon sets release and popularity rankings shift.
3. As the operator, I want `update_catalog.py` to read the scrape output and mark matching `cardmarket_products` rows with `is_curated = 1` and a `popularity_rank`, so that normalization prompts can filter and sort candidates correctly.
4. As the operator, I want the schema change to be additive (new columns only, no FK changes), so that existing mappings and the review UI are not disrupted.
5. As the operator, I want a calibration session prompt that selects 25 raw_names by frequency and retailer diversity, so that examples cover the highest-volume products and the widest range of naming styles.
6. As the operator, I want the calibration prompt to show me the top 5 curated catalog candidates for each raw_name in popularity order, so that I can pick the correct match without doing manual lookups.
7. As the operator, I want to record not just my chosen mapping but also why it is correct and why the top rejected candidates do not match, so that the LLM has contrastive signal to learn from.
8. As the operator, I want calibration examples stored in a structured markdown file, so that they can be referenced as few-shot context in the batch normalization prompt.
9. As the operator, I want the batch normalization prompt to process 100 raw_names at a time using the curated catalog, calibration examples, and the improved classification rule, so that I can verify output in manageable chunks.
10. As the operator, I want the batch prompt to use popularity rank as a soft prior (prefer higher-ranked candidates when two are equally plausible), so that products actually stocked in Finland are matched first.
11. As the operator, I want each batch to output a CSV with `scraped_name`, `proposed_mapping`, and `confidence` columns, so that I can review it in a spreadsheet tool.
12. As the operator, I want to only annotate incorrect rows in the verification CSV (correct rows need no action), so that review is fast for high-accuracy batches.
13. As the operator, I want `apply_batch.py` to accumulate verified batch CSVs into a local draft file without touching the production database, so that I can verify the entire pipeline before committing.
14. As the operator, I want `apply_batch.py --finalize` to atomically wipe `name_mappings` and bulk-insert all accumulated mappings on the Hetzner server, so that the swap is clean and production is never in a partially-updated state.
15. As the operator, I want the finalize step to run the `price_readings.product_id` backfill immediately after inserting, so that all historical price readings are linked to their products without a separate step.
16. As the operator, I want genuinely unrecognizable raw_names (garbled text, encoding errors, non-product listings) to be written as `status='undecided'` at finalization, so that the existing Mapping Review UI can handle them without any UI changes.
17. As the operator, I want the existing `name_mappings` table and `price_readings` linkage to remain fully live throughout the rebuild, so that the scraper and UI continue working in production while new mappings are prepared.
18. As the operator, I want the classification rule to be "include if the product belongs to one of the 8 curated Cardmarket categories; null_map everything else," so that scope is unambiguous and non-TCG items are excluded.

## Implementation Decisions

### Schema change — `cardmarket_products`
- Add `is_curated` (INTEGER, NOT NULL DEFAULT 0) column.
- Add `popularity_rank` (INTEGER, nullable) column.
- No new tables, no FK changes, no data migration. The existing 5,006 rows all default to `is_curated = 0`.
- Applied via `ALTER TABLE` on the Hetzner server; `schema.sql` updated to match.

### Catalog scrape prompt (`copilot_prompts/scrape_catalog.md`)
- Navigates the 8 Cardmarket category pages (Boosters, Booster Boxes, Theme Decks, Trainer Kits, Tins, Box Sets, Elite Trainer Boxes, Blisters).
- Paginates up to 10 pages per category (30 products per page; ~2,400 products max across all categories).
- Captures per product: `cardmarket_product_id` (from product URL), `name`, `category`, `popularity_rank` (1 = most popular within its category page).
- Output: a single JSON file, one object per product.
- Operator handles the captcha manually; the prompt handles all navigation and pagination.
- Designed to be re-run quarterly or when a major new set releases.

### `update_catalog.py`
- Reads the JSON output of the scrape prompt.
- SSHes into the Hetzner server (same pattern as `llm_normalise.md`).
- For each entry: matches by `cardmarket_product_id` (exact integer match), sets `is_curated = 1` and `popularity_rank`.
- Products in the existing DB not present in the scrape output remain `is_curated = 0`.
- Reports: matched count, not-found count (products in scrape not in DB — should be near-zero).
- Idempotent: safe to re-run after a fresh scrape.

### Calibration session prompt (`copilot_prompts/llm_calibrate.md`)
- Queries the Hetzner server for the 25 raw_names with the highest `price_readings` count, ensuring at least one raw_name per large retailer cluster (hobby shops, big chains, Swedish-language sites).
- For each raw_name: presents the top 5 candidates from `cardmarket_products WHERE is_curated = 1`, ordered by `popularity_rank` ascending (most popular first).
- Operator input per product: chosen mapping (or "none") + reasoning for the match + brief note on why the top rejected candidates do not match.
- All 25 annotated examples are written to `copilot_prompts/calibration_examples.md`.
- Example format in the markdown: raw_name, top-5 candidates shown, chosen mapping (name + product ID, or null), why it matched, why each rejected candidate didn't.

### Batch normalization prompt (`copilot_prompts/llm_batch_normalise.md`)
- Supersedes `llm_normalise.md` as the primary normalization tool; the old prompt is kept as a fallback for quick one-off mappings.
- Fetches all raw_names not yet present in the local draft accumulation file (to avoid re-processing verified rows).
- Processes in batches of 100.
- Prompt context includes: full `calibration_examples.md`, curated catalog sorted by `popularity_rank`, classification rule (the 8 categories = in-scope; all else = `null_mapped`), Finnish→English translation glossary carried over from `llm_normalise.md`.
- Soft prior: when two candidates are equally plausible, prefer the one with lower `popularity_rank` (higher popularity).
- Status assignments: `mapped` (confident match to a curated product), `null_mapped` (confirmed not a sealed TCG product), `undecided` (rare fallback for genuinely unrecognizable text — not a substitute for low confidence).
- Output per batch: CSV file with columns `raw_name`, `proposed_name`, `cardmarket_product_id`, `confidence`, `status`.
- After outputting each CSV, pauses for operator review before the next batch.

### `apply_batch.py` — two-mode script
- **Accumulate mode** (default, called after each verified batch): reads the verified batch CSV, appends rows to a local `draft_mappings.json` file. Duplicate `raw_name` entries overwrite earlier entries (idempotent).
- **Finalize mode** (`--finalize`): reads `draft_mappings.json`, SSHes to Hetzner, executes in a single transaction: DELETE all rows from `name_mappings`, bulk-INSERT all accumulated rows, run `price_readings.product_id` backfill. Reports final counts by status.
- The production `name_mappings` table on Hetzner is not touched until `--finalize` is explicitly called.
- `undecided` rows are included in the finalize write with `status='undecided'` and `llm_suggestion_id` set to the best-guess `cardmarket_product_id`.

### Classification rule (encoded in the batch prompt)
- **`mapped`**: raw_name refers to a product in `cardmarket_products WHERE is_curated = 1`. `cardmarket_product_id` set.
- **`null_mapped`**: non-Pokémon products; individual cards/singles; posters, sleeves, playmats, figures; products from other TCG brands; any product whose category is not one of the 8 curated categories.
- **`undecided`**: raw_name is garbled, too short to interpret, or in an unknown language/encoding. Not used for "I'm not sure which product this is."

### Shadow mode invariant
- The 292 currently-`mapped` and 279 currently-`null_mapped` rows in `name_mappings` remain active throughout the rebuild.
- New `price_readings` continue to get `product_id` assigned at scrape time (via the existing DB lookup) for any raw_name that was previously `mapped`.
- Shadow mode ends only when `--finalize` is called.

## Testing Decisions

No automated tests. All verification is manual: the operator reviews and annotates batch CSVs before calling `--finalize`. The calibration session is the primary quality gate.

## Out of Scope

- Automatic normalization on new scrape runs (manual CLI only, consistent with the initial overhaul).
- Handling products that exist in Finland but are absent from all 8 Cardmarket category pages.
- Per-site overrides for the same raw_name (raw_name key remains global).
- Changes to the Mapping Review UI.
- Confidence threshold tuning or automated quality metrics.
- Pagination beyond 10 pages per Cardmarket category.

## Further Notes

- After `--finalize`, the `undecided` queue in the Mapping Review UI should be significantly smaller than the current 728. Residual undecided rows are handled through the existing review UI.
- The full 5,006-row `cardmarket_products` dataset remains in the DB; only the `is_curated = 1` filter narrows the candidate set used by normalization prompts.
- `llm_normalise.md` is superseded but not deleted — it remains usable for quick ad-hoc mappings.
