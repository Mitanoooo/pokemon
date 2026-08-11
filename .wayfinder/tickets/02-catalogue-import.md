# 02 — Catalogue import script

## Question

How does `cardmarket_catalogue.json` get loaded into the `cardmarket_products` table?

- A one-off CLI script (or `init_db.py` extension) that reads the JSON and bulk-inserts
- Must be idempotent (INSERT OR IGNORE on idProduct)
- Should live next to `init_db.py` or be folded into it

**Status: CLOSED**

## Resolution

`scripts/import_catalogue.py` — standalone CLI, idempotent (`INSERT OR IGNORE` on `idProduct` PK). Kept separate from `init_db.py` (schema-only) because it requires the JSON file to be present and is a deliberate one-off data load, not part of schema initialisation.

Run: `python scripts/import_catalogue.py [--db pokemon.db] [--catalogue cardmarket_catalogue.json]`

Result: 5006 rows inserted into `cardmarket_products` on 2026-08-11. Re-run reports 0 inserted / 5006 skipped.

Blocking: 01 (table must exist first)
Blocked by this: 03, 04
