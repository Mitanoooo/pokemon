# 04 — Review UI (Streamlit page)

## Question

What does the mapping review page look like and how does it work?

- New page in `app/views/` 
- Lists all `name_mappings` rows with `status = undecided`, one row per raw_name
- Each row shows: raw_name, sites it appeared on, reading count, LLM suggestion + confidence if present
- Dropdown: first option "— Not a Pokémon product", then cardmarket products grouped by category; categories sorted by COUNT of existing `mapped` rows pointing to products in that category (descending); within category, products sorted by their own mapping count
- On selection: immediately writes to `name_mappings` (status → mapped or null_mapped) and backfills `price_readings.product_id`
- LLM suggestion pre-selects the dropdown default

**Status: CLOSED**

## Resolution

`app/views/mappings.py` — new "Mapping Review" Streamlit page, wired into `app/main.py`.

**Behaviour:**
- Lists all `name_mappings` rows with `status='undecided'`, sorted by reading count desc
- Each row shows: raw_name, site(s), reading count, LLM suggestion + confidence
- Dropdown: first option "— Not a Pokémon product", then all 5006 cardmarket products grouped by category (categories sorted by existing mapping count desc, products within category sorted by their own mapping count)
- Section header rows (e.g. `── Pokémon Display ──`) are non-selectable; clicking one is a no-op
- On selection: immediately calls `db.save_mapping()` which writes `name_mappings` status + backfills `price_readings.product_id`
- LLM suggestion pre-selects dropdown default when present
- Cache cleared on each save so counts stay live

**New db.py functions:** `get_undecided_mappings`, `get_cardmarket_products_for_dropdown`, `save_mapping`

**Note:** `GROUP_CONCAT ... ORDER BY` not used — SQLite on server is 3.40, which doesn't support it.

Blocking: 01, 02
Blocked by this: nothing (can be built in parallel with 03)
