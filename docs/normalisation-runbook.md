# Normalisation Runbook

The normalisation workflow maps raw product names scraped from retailer pages to clean canonical names (e.g. "Prismatic Evolutions — Elite Trainer Box"). Until a raw name is mapped, it appears on the **Unknowns** page in Streamlit and does not contribute to the Products page, price history, or digest alerts.

The workflow is:

1. **Export** — dump all unmapped raw names from the database to a JSON file
2. **Claude** — paste the file into a Claude session to get canonical name suggestions
3. **Import** — load the mappings back into the database
4. **Verify** — confirm the Unknowns page is clear and Products page is populated

---

## When to run

- After the **first scraper run** on a new server — run normalisation before enabling the digest so alerts only fire on named products.
- Whenever the **Unknowns page** in Streamlit shows unmapped names — check weekly or after any scraper run that produced new products.

---

## Step 1 — Export unmapped names

```bash
cd /opt/pokemon
venv/bin/python -m scraper.normaliser export
```

This writes `pending_names.json` in the project root. The file lists every raw name that has appeared in `price_readings` but has no entry in `product_aliases` (see also `docs/normaliser_example_input.json`):

```json
[
  {
    "raw_name": "Pokemon TCG: Prismatic Evolutions Booster Box",
    "site": "Poromagia"
  },
  {
    "raw_name": "Pokémon TCG: Scarlet & Violet—Twilight Masquerade Elite Trainer Box",
    "site": "TCG Kauppa"
  }
]
```

The `site` field is metadata only — it is ignored on import. Only `raw_name` is used.

If the output is `0 unmapped name(s) written to pending_names.json`, there is nothing to do — all names are already mapped.

To write to a custom path (useful for incremental runs): `venv/bin/python -m scraper.normaliser export new_names.json`

---

## Step 2 — Send to Claude

Open a Claude session (claude.ai or the company AWS Bedrock deployment) and paste the following prompt, replacing `<paste JSON here>` with the full contents of `pending_names.json`:

```
You are helping me build a Pokémon sealed product price tracker.
Below is a JSON array of raw product names scraped from Finnish retailer websites.
For each entry, add a "canonical_name" field: a short, clean English name in the format
"<Set Name> — <Product Type>", e.g. "Prismatic Evolutions — Elite Trainer Box".

Rules:
- Use the official English set name (not Finnish or abbreviated forms).
- Product types: Booster Box, Booster Bundle, Elite Trainer Box, Tin, Blister Pack, Collection Box.
- Strip retailer-specific prefixes like "Pokemon TCG:", "Pokémon TCG:", pack counts in parentheses, etc.
- If two raw names refer to the same product, give them the same canonical_name.
- Return only the JSON array with the added "canonical_name" field. No prose.

<paste JSON here>
```

Claude will return the same JSON array with a `canonical_name` field added to each entry. Save it to `mappings.json` in the project root.

---

## Step 3 — Import mappings

```bash
cd /opt/pokemon
venv/bin/python -m scraper.normaliser import mappings.json
```

Example output:

```
aliases created: 47, products created: 23, skipped: 0
```

- **aliases created** — raw names successfully mapped
- **products created** — new canonical products inserted into `products`
- **skipped** — entries where the raw name had no matching `price_readings` row (Claude-invented names that were never scraped), or where the alias already existed

A non-zero `skipped` count is normal and harmless.

---

## Step 4 — Verify

1. **Unknowns page** — open Streamlit and navigate to Unknowns. If all names were mapped, the table should be empty (or show only names scraped since the export was taken).

2. **Products page** — canonical products should now appear, grouped by category, with price history.

3. **Count check** — compare `aliases created` from the import output against the count from the export: they should match (minus any legitimately skipped entries).

If a product has a wrong canonical name, correct it directly on the Products page in Streamlit — the import never overwrites existing canonical names, so corrections survive re-runs.

---

## Re-running and incremental updates

The import is **idempotent**: re-running with the same file produces `skipped: N, aliases created: 0` — no duplicates are created. It is safe to re-run.

For incremental updates (new raw names from a later scraper run):

1. Run `venv/bin/python -m scraper.normaliser export new_names.json` — only names with no existing alias are exported.
2. Repeat the Claude and import steps with `new_names.json`.

Already-mapped names are never re-exported.
