# 11 — apply_batch.py

## Question

Write a two-mode script (`scripts/apply_batch.py`) for accumulating verified batches and finalizing them to production.

**Accumulate mode** (default — called after each verified batch):
- Reads a verified batch CSV
- Appends rows to `draft_mappings.json` (local file, not on Hetzner)
- Duplicate `raw_name` entries overwrite earlier entries (idempotent)
- Reports: rows added, rows overwritten

**Finalize mode** (`--finalize` — called once when all batches are verified):
- Reads `draft_mappings.json`
- SSHes into the Hetzner server (same pattern as `llm_normalise.md`)
- In a single transaction: DELETE all rows from `name_mappings`, bulk-INSERT all accumulated rows
- Runs `price_readings.product_id` backfill immediately after insert
- Reports final counts by status (mapped / null_mapped / undecided), and backfill count

The production `name_mappings` table on Hetzner is never touched until `--finalize` is explicitly called. `undecided` rows are included in the finalize write with `status='undecided'` and `llm_suggestion_id` set to the best-guess `cardmarket_product_id`.

**Status: OPEN**

Blocking: 12
Blocked by: nothing (can be built before batches are run)
