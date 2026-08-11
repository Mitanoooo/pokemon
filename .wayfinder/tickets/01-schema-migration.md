# 01 — Schema migration

## Question

What does the new SQLite schema look like, and what migration steps are needed to move from the current schema to it?

Specifically:
- Define `cardmarket_products` table (columns from JSON: idProduct, name, idCategory, categoryName, idExpansion, dateAdded)
- Define `name_mappings` table (raw_name PK, cardmarket_product_id FK nullable, llm_suggestion_id FK nullable, confidence REAL, status TEXT, mapped_at TEXT)
- Alter `price_readings` and `thresholds` to FK into `cardmarket_products` instead of `products`
- Drop `products`, `product_aliases`, `categories`
- Migration script that runs against the live DB (must be idempotent / safe to re-run)

**Status: CLOSED**

## Resolution

New schema live in `schema.sql`. Migration run against `pokemon.db` on 2026-08-11.

**New tables:**
- `cardmarket_products(id PK, name, id_category, category_name, id_expansion, date_added)` — imported from cardmarket_catalogue.json; `id` is the cardmarket `idProduct` integer
- `name_mappings(raw_name PK, cardmarket_product_id FK nullable, llm_suggestion_id FK nullable, confidence REAL, status CHECK('mapped'|'null_mapped'|'undecided'), mapped_at)` — one row per distinct scraped name

**Removed:** `products`, `product_aliases`, `categories`

**Migrated:** `price_readings.product_id` and `thresholds.product_id` now FK into `cardmarket_products`. All 2658 existing price_readings preserved; product_id stays NULL until catalogue import + LLM pass runs.

**Artefacts:** `schema.sql`, `scripts/migrate_v2.py`, `init_db.py`

Blocking: nothing — can start immediately.
Blocked by this: 02, 03, 04
