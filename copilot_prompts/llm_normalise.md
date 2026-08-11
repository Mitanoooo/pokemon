# LLM Normalisation Pass

Your job is to map every unmapped scraped product name to the correct Cardmarket product entry, or mark it as not a tracked product. Results are written directly to `pokemon.db`.

## Context

The SQLite database at `pokemon.db` (project root) has two relevant tables:

**`name_mappings`** — one row per distinct raw scraped name:
- `raw_name TEXT PRIMARY KEY`
- `cardmarket_product_id INTEGER` — FK into `cardmarket_products.id`; NULL for junk/non-product
- `llm_suggestion_id INTEGER` — your best guess when confidence is below threshold
- `confidence REAL` — your confidence 0.0–1.0
- `status TEXT` — one of: `'mapped'`, `'null_mapped'`, `'undecided'`
- `mapped_at TEXT` — datetime string, set when status is mapped or null_mapped

**`cardmarket_products`** — the authoritative catalogue (5006 rows):
- `id INTEGER` — the Cardmarket product ID (use this as the FK value)
- `name TEXT` — product name, e.g. "Scarlet & Violet Booster Box"
- `category_name TEXT` — e.g. "Pokémon Display", "Pokémon Booster", "Pokémon Elite Trainer Boxes"

Categories in the catalogue (all are sealed Pokémon TCG products):
- Pokémon Box Set, Pokémon Booster, Pokémon Display, Pokémon Tins, Pokémon Blisters,
  Pokémon Theme Deck, Pokémon Elite Trainer Boxes, Pokémon Coins, Pokémon Lot,
  Pokémon Trainer Kits, PCG Set, Pokémon Pokémon Sets

## Your task

### Step 1 — fetch unmapped names

Run this query to get all raw names not yet mapped:

```python
import sqlite3
conn = sqlite3.connect('pokemon.db')
rows = conn.execute("""
    SELECT DISTINCT raw_name FROM price_readings
    WHERE raw_name NOT IN (SELECT raw_name FROM name_mappings)
    ORDER BY raw_name
""").fetchall()
names = [r[0] for r in rows]
print(f"{len(names)} names to process")
conn.close()
```

### Step 2 — load the catalogue

```python
conn = sqlite3.connect('pokemon.db')
catalogue = conn.execute(
    "SELECT id, name, category_name FROM cardmarket_products ORDER BY name"
).fetchall()
conn.close()
# catalogue is a list of (id, name, category_name)
```

### Step 3 — map names in batches of 50

Process names 50 at a time. For each batch, assess each raw name:

**Mapping rules:**
- If the name clearly refers to a specific sealed Pokémon TCG product in the catalogue → `status='mapped'`, set `cardmarket_product_id` to the matching `id`, confidence ≥ 0.85
- If the name is clearly NOT a sealed Pokémon TCG product (toy, plush, binder, costume, figure, puzzle, coin, etc.) → `status='null_mapped'`, `cardmarket_product_id=NULL`, confidence ≥ 0.85
- If you can make a reasonable guess but aren't sure → `status='undecided'`, set `llm_suggestion_id` to your best guess id, confidence < 0.85
- If you have no idea → `status='undecided'`, `llm_suggestion_id=NULL`, `confidence=NULL`

**Matching tips:**
- Finnish product names often describe the same product: "Boosterpakkaus" = Booster, "Boosteri" = Booster, "Näyttölaatikko"/"Display" = Booster Box, "Elite Trainer Box"/"ETB" = Elite Trainer Box
- Match on set name + product type. E.g. "Pokemon Scarlet & Violet Booster" → find the "Scarlet & Violet Booster" entry in the catalogue
- When multiple catalogue entries could match (e.g. individual booster vs booster box), pick the one that best fits the name
- Accessories, collectibles, toys, clothing, puzzles, binders, and figures are NOT tracked products → null_mapped

### Step 4 — insert results

After assessing each batch, insert with this pattern:

```python
import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('pokemon.db')
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

batch_results = [
    # Each entry: (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status)
    # Examples:
    # ("Pokemon Scarlet & Violet Booster", 12345, None, 0.95, "mapped"),
    # ("Pokemon Pikachu Pehmolelu 20cm",   None,  None, 0.98, "null_mapped"),
    # ("Pokemon Mystery Box",               67890, None, 0.70, "undecided"),
]

for raw_name, cm_id, suggestion_id, conf, status in batch_results:
    mapped_at = now if status in ('mapped', 'null_mapped') else None
    conn.execute("""
        INSERT OR IGNORE INTO name_mappings
            (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (raw_name, cm_id, suggestion_id, conf, status, mapped_at))

conn.commit()
conn.close()
```

Use `INSERT OR IGNORE` so re-runs are safe.

### Step 5 — report

After all batches, print a summary:

```python
conn = sqlite3.connect('pokemon.db')
stats = dict(conn.execute("""
    SELECT status, COUNT(*) FROM name_mappings GROUP BY status
""").fetchall())
print("Results:", stats)
conn.close()
```

## Important notes

- Commit after each batch of 50 so progress is saved if the session is interrupted
- Re-check remaining unmapped names at the start of each batch (in case of retries): re-run the Step 1 query each time
- Do not insert duplicate rows — `INSERT OR IGNORE` handles this
- When in doubt between two similar catalogue entries, prefer the more specific one (e.g. "Booster Box" over "Booster" if the name says "booster box")
- The confidence threshold for auto-commit is **0.85** — anything below goes to `undecided`
