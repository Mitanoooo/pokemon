# 13 — Four-table schema and DB rebuild script

## Question

Rewrite `schema.sql` down to four tables and write `scripts/rebuild_db.py` to produce a new DB file from the current one. See [spec](../spec-tracker-refocus.md) → "Schema (the whole DB)" and "Rebuild, not migrate".

**`schema.sql` after this ticket** contains `sites`, `scrape_runs`, `listings`, `updates` and nothing else.

- `sites`: existing columns plus `availability_mode TEXT` (comma-joined resolution forms, NULL = no availability block in config).
- `listings`: drops `product_id` and `latest_in_stock`; adds `availability TEXT NOT NULL DEFAULT 'unknown'` with a CHECK over `in_stock|out_of_stock|preorder|unknown`, `availability_text TEXT`, `from_preorder_url INTEGER NOT NULL DEFAULT 0`.
- `updates`: drops `product_id`; `event_type` CHECK becomes `new_listing|new_preorder|back_in_stock|price_drop|price_rise`.
- Indexes: `listings(raw_name)`, `listings(site_id, availability)`, `updates(created_at DESC)`, `updates(event_type, created_at DESC)`.
- Gone: `cardmarket_products`, `name_mappings`, `thresholds`, `price_readings`.

`init_db.py` updated to match.

**`scripts/rebuild_db.py`**

```
python scripts/rebuild_db.py --source pokemon.db [--target pokemon.db.new] [--force]
```

- Creates the target from `schema.sql`; refuses to overwrite an existing target without `--force`.
- Copies `sites` verbatim (`availability_mode` stays NULL; the next scrape run fills it).
- Copies `scrape_runs` verbatim.
- Copies `listings` minus `product_id`, translating `latest_in_stock`: `1` → `in_stock`, `0` → `out_of_stock`, `NULL` → `unknown`. `availability_text` NULL, `from_preorder_url` 0.
- Copies `updates` minus `product_id`. `price_change` becomes `price_drop` or `price_rise` by float-comparing `old_value` and `new_value`; a row where either side does not parse is skipped and counted. Other event types pass through.
- Prints per-table source and target counts plus the skipped count, and exits non-zero if any table's target count is unexpectedly lower.

**Deploy note (applies to this ticket and 14 together):** merge 13 and 14 first so no code queries a dropped table, then on Hetzner, mid-hour because cron scrapes at `:00`:

```
cd /opt/pokemon
sudo -u pokemon venv/bin/python scripts/rebuild_db.py --source pokemon.db
# verify the printed counts
mv pokemon.db pokemon.db.pre-refocus-$(date +%Y%m%d)
mv pokemon.db.new pokemon.db
chown pokemon:pokemon pokemon.db
systemctl restart pokemon-streamlit
```

The archived file is the only remaining copy of the 395,722 price readings. Keep it.

**Tests:** `tests/test_rebuild_db.py` per the spec's testing decisions.

**Status: DONE**

Notes from the build: `init_db.py` lost its pre-v2/pre-v3 `ALTER TABLE` helpers — moving an
existing DB to a new shape is `rebuild_db.py`'s job now. A `price_change` row whose old and new
values parse but are equal has no direction to pick, so it is skipped and counted with the
unparseable ones. Until ticket 14 lands, the test suite is red: `test_db.py`, `test_runner.py`,
`test_writeback_db.py`, `test_app_db.py` and `test_digest.py` all build fixtures from `schema.sql`
and query dropped tables.

Blocking: 14, 15, 19, 20
Blocked by: nothing
