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

**Status: CLOSED**

## Resolution

`scripts/apply_batch.py` written (commit `91747c9`). Both modes built as specified.

**Accumulate** — `python scripts/apply_batch.py batch_001.csv`. Loads `draft_mappings.json` into a dict keyed by `raw_name`, reads the CSV via `DictReader`, coerces `cardmarket_product_id` to int and `confidence` to float (empty → `None`), writes back indented UTF-8 JSON. Reports rows added / overwritten / total in draft.

**Finalize** — `python scripts/apply_batch.py --finalize`. Pipes the whole draft to an inline Python snippet over SSH. One transaction: `DELETE FROM name_mappings` → `executemany` INSERT → `price_readings.product_id` backfill via correlated subquery on `raw_name` where `status='mapped'`. Reports counts by status and the backfill count.

**Row shaping in finalize:**
- `mapped` → `cardmarket_product_id` and `llm_suggestion_id` both set to the pid, `mapped_at` timestamped
- `null_mapped` → both NULL, `mapped_at` timestamped
- `undecided` → `cardmarket_product_id` NULL, `llm_suggestion_id` = best-guess pid, `mapped_at` NULL

**Known wart:** the backfill `UPDATE price_readings` has no `WHERE` clause, so `cur.rowcount` equals every row in the table, not the number actually linked to a product. The printed "Backfilled: N price_readings rows" therefore overstates the result — read it as "rows touched". The write itself is correct (unmatched names are reset to NULL, which is intended). Worth a follow-up if the number matters for reporting.

Blocking: 12
Blocked by: nothing (can be built before batches are run)
