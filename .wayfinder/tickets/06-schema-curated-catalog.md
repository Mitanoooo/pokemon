# 06 — Schema: curated catalog columns

## Question

Add `is_curated` and `popularity_rank` columns to `cardmarket_products` on the Hetzner server and update `schema.sql` to match.

- `is_curated` INTEGER NOT NULL DEFAULT 0
- `popularity_rank` INTEGER (nullable)

Applied via `ALTER TABLE`. No data migration needed — all 5,006 existing rows default to `is_curated = 0`.

**Status: CLOSED**

## Resolution

`ALTER TABLE` run on Hetzner 2026-08-12. Both columns added to the live DB:
- `is_curated INTEGER NOT NULL DEFAULT 0` — all 5,006 existing rows set to 0
- `popularity_rank INTEGER` (nullable) — all existing rows set to NULL

`schema.sql` updated to match. Idempotent: the migration checks existing columns before altering.

Blocking: 08, 09, 10
