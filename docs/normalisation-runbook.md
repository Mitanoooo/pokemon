# Normalisation Runbook

The normalisation workflow maps raw product names scraped from retailer pages to clean canonical names (e.g. "Prismatic Evolutions — Elite Trainer Box"). Until a raw name is mapped, it appears on the **Unknowns** page in Streamlit and does not contribute to the Products page, price history, or digest alerts.

The workflow is:

1. **Export** — dump all unmapped raw names from the database to a JSON file
2. **Generate mappings** — run `scripts/build_canonical_mappings.py`, a heuristic script that adds canonical names automatically
3. **Import** — load the mappings back into the database
4. **Verify** — confirm the Unknowns page is clear and Products page is populated

Step 2 used to be "paste `pending_names.json` into a Claude session" — that doesn't scale once the export runs into the thousands of names (most retailer Pokémon-category pages return a lot of non-TCG merchandise alongside real sealed products). `scripts/build_canonical_mappings.py` replaces that manual step: it recognises known set names, sealed-product types, and known merch keywords, and only emits a `canonical_name` when it's confident. Anything it can't confidently classify (plush, figures, Funko Pops, binders, sleeves, apparel, obscure/garbled listings, single cards, etc.) is deliberately left unmapped rather than guessed — it stays on the Unknowns page for a later incremental pass, exactly as intended by this workflow's incremental design (see "Re-running and incremental updates" below).

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

## Step 2 — Generate canonical name mappings

```bash
cd /opt/pokemon
venv/bin/python scripts/build_canonical_mappings.py pending_names.json
```

This reads `pending_names.json` and writes `mappings.json` in the project root, printing a summary:

```
mapped: 494
skipped (merch/non-sealed): 364
skipped (no confident set/type match): 446

unique canonical products: 165
```

How it decides a `canonical_name`:

- **`SKIP_KEYWORDS`** — keywords that mean "this is merch, not a sealed TCG product" (plush, figures, Funko, binders, sleeves, apparel, puzzles, LEGO/Topps/MTG crossovers, etc.) — matching entries are left unmapped.
- **`TYPE_PATTERNS`** — regexes that detect the sealed-product type (Booster Box, Booster Bundle, Elite Trainer Box, Tin, Blister Pack, Collection Box, plus real-world extensions the data needed: Booster Pack, Battle Deck, Build & Battle Box, Checklane Blister, Gift Box, etc.).
- **`SET_NAMES`** — a curated, longest-match-first list of known Pokémon TCG expansion / product-line names (official English names, the 2026 "Mega Evolution" sub-sets, Pokémon GO, and known Japanese/S-Chinese exclusive print runs), plus `SET_NAME_ALIASES` to collapse spelling variants (e.g. "Paradoxrift" / "Paradox Rift") to one canonical spelling.
- A few special cases for messy real-world formatting: a bracket regex that pulls the specific subset name out of `"... - <Subset> (<CODE>) - Booster ..."` listings (common on Japanese/Chinese exclusive prints) instead of falling back to a generic era name, and a dedicated case for the "First Partner Illustration Collection Series N" product line.

An entry only gets a `canonical_name` when **both** a product type and a set name are confidently identified — if either is missing, it's left out of `mappings.json` and stays unmapped.

### Reviewing / extending it

Before importing, sanity-check the output — this script needs occasional tuning as new sets release or new retailers get scraped:

```bash
venv/bin/python scripts/build_canonical_mappings.py pending_names.json --dump-skipped-dir /tmp/norm
```

- Skim `mappings.json` (or group by `canonical_name`) for anything that looks wrong — e.g. a generic era name swallowing a specific sub-set, or two spellings of the same set producing two different canonical names. Fix by adding an entry to `SET_NAME_ALIASES`, or making an existing `SET_NAMES` entry more specific / reordering it (entries are matched in list order, so put more specific names before generic ones).
- Skim `/tmp/norm/skipped_no_match.txt` (things that *do* look like real sealed products but weren't recognised) for new set names or product-type wording to add to `SET_NAMES` / `TYPE_PATTERNS`, then re-run the script.
- `/tmp/norm/skipped_merch.txt` should be almost entirely genuine non-sealed merchandise — if real sealed products show up there, remove/narrow the `SKIP_KEYWORDS` entry that caught them.
- It's fine — expected, even — to leave a large chunk unmapped on any given run. Only import what you're confident about; the rest is still there next time via `export`.

If you'd rather have an LLM take a pass at the ones the script skipped (e.g. hand this off to a Claude session), export just `skipped_no_match.txt`'s raw names and use the same rules as the script: format `"<Set Name> — <Product Type>"`, official English set names, same product-type list. Merge its output into `mappings.json` before importing.

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
- **skipped** — entries where the raw name had no matching `price_readings` row (shouldn't happen with `build_canonical_mappings.py` output, since it only maps names taken directly from the export — but can happen with hand-edited/LLM-invented mappings), or where the alias already existed

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
2. Run `venv/bin/python scripts/build_canonical_mappings.py new_names.json --mappings-out new_mappings.json`.
3. Repeat the import step with `new_mappings.json`.

Already-mapped names are never re-exported. Each incremental run is also a good opportunity to check whether `scripts/build_canonical_mappings.py`'s `SET_NAMES`/`TYPE_PATTERNS` need updating for newly-released sets before generating the mappings.
