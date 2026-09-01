# 01 — Schema migration: scrape_runs, listings, updates, price_readings.run_id

**What to build:** Three new tables and one new column land in the database so every subsequent ticket has a stable schema to build against. The app must still start and all existing pages must still work after the migration.

New tables to add to `schema.sql`:

- `scrape_runs` — one row per `run_all_sites()` invocation: `id`, `started_at`, `finished_at`.
- `listings` — one row per distinct `(site_id, raw_name)` pair ever seen: `site_id`, `raw_name` (composite PK), `product_id` (FK to `cardmarket_products`, nullable), `product_url`, `first_seen_at`, `last_seen_at`, `last_run_id` (FK to `scrape_runs`), `latest_price` (nullable), `latest_currency`, `latest_in_stock`.
- `updates` — materialised event log: `id`, `run_id` (FK to `scrape_runs`), `site_id` (FK to `sites`), `raw_name`, `product_id` (nullable FK to `cardmarket_products`), `event_type` (CHECK IN `price_change`, `new_listing`, `back_in_stock`), `old_value`, `new_value`, `created_at`, `seen` (INTEGER DEFAULT 0).

Column to add to `price_readings`: `run_id INTEGER REFERENCES scrape_runs(id)` — nullable so existing rows are unaffected.

The migration on Hetzner is three `CREATE TABLE IF NOT EXISTS` statements plus one `ALTER TABLE price_readings ADD COLUMN run_id`. `schema.sql` is updated to match so fresh installs pick up the new shape automatically.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `schema.sql` contains all three new table definitions and the `run_id` column on `price_readings`.
- [ ] Migration applied on Hetzner: `CREATE TABLE IF NOT EXISTS` for each new table, `ALTER TABLE price_readings ADD COLUMN run_id INTEGER REFERENCES scrape_runs(id)` for the column.
- [ ] `python -m pytest tests/` passes with the updated schema (the in-memory fixture in `tests/test_db.py` reads `schema.sql` directly, so it exercises the new DDL automatically).
- [ ] The Streamlit app starts on Hetzner and all existing pages (Products, Mapping Review, Site Health, Unknowns, Categories, Thresholds) load without error after the migration.
