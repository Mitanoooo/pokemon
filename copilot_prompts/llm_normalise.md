# LLM Mapping — Claude Code prompt

Paste this prompt into a Claude Code session. It will SSH into the Hetzner server, fetch all unmapped names, map them against the Cardmarket catalogue, and write the results back.

---

Your task is to map every unmapped raw product name on the Hetzner server to the correct Cardmarket product entry, or mark it as not a tracked product.

## Connection

The database is on the Hetzner server. Use SSH throughout — do not copy the DB locally.

```
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63
```

Working directory on server: `/opt/pokemon`
Database: `/opt/pokemon/pokemon.db`
Python: `/opt/pokemon/venv/bin/python`

## Step 1 — fetch unmapped names and catalogue

Run this on the server to get what needs mapping:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
names = [r[0] for r in conn.execute('''
    SELECT DISTINCT raw_name FROM price_readings
    WHERE raw_name NOT IN (SELECT raw_name FROM name_mappings)
    ORDER BY raw_name
''').fetchall()]
print(len(names), 'unmapped names')
for n in names: print(n)
conn.close()
\""
```

And fetch the catalogue:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
for row in conn.execute('SELECT id, name, category_name FROM cardmarket_products ORDER BY name'):
    print(row[0], '|', row[1], '|', row[2])
conn.close()
\""
```

## Step 2 — assess each name

For each unmapped raw name, decide:

- **mapped** — clearly refers to a specific sealed Pokémon TCG product in the catalogue → `status='mapped'`, set `cardmarket_product_id` to the matching `id`, `confidence ≥ 0.85`
- **null_mapped** — clearly NOT a sealed Pokémon TCG product (toy, plush, figure, costume, puzzle, other TCG brand, etc.) → `status='null_mapped'`, `cardmarket_product_id=NULL`, `confidence ≥ 0.85`
- **undecided** — uncertain → `status='undecided'`, set `llm_suggestion_id` to your best guess id, `confidence < 0.85`

**Matching tips:**
- Finnish terms: "Boosterpakkaus"/"Boosteri" = Booster, "Näyttölaatikko"/"Display" = Booster Box/Display, "ETB"/"Elite Trainer Box" = Elite Trainer Box
- Match on set name + product type
- Non-Pokémon brands (Lorcana, MTG, FIFA/Panini, Topps, Funko, LEGO, Mega Construx) → null_mapped
- Toys, plush, figures, costumes, puzzles, binders, sleeves, playmats → null_mapped
- Individual promo cards (pattern: "Name – Set #NNN") → null_mapped

## Step 3 — write results to the server

After assessing all names, write them in batches of 50. Run this for each batch:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3
from datetime import datetime, timezone
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
batch = [
    # (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status)
    # e.g. ('Scarlet & Violet Booster Pack', 12345, None, 0.95, 'mapped'),
    # e.g. ('Funko POP Pikachu', None, None, 0.98, 'null_mapped'),
    # e.g. ('Mystery Pokemon Box', 67890, None, 0.70, 'undecided'),
]
for raw_name, cm_id, sugg_id, conf, status in batch:
    mapped_at = now if status in ('mapped', 'null_mapped') else None
    conn.execute('''
        INSERT OR IGNORE INTO name_mappings
            (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (raw_name, cm_id, sugg_id, conf, status, mapped_at))
conn.commit()
print('Inserted', len(batch), 'rows')
conn.close()
\""
```

## Step 4 — backfill price_readings.product_id

After all batches are written, run this once:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
updated = conn.execute('''
    UPDATE price_readings
    SET product_id = (
        SELECT cardmarket_product_id FROM name_mappings
        WHERE name_mappings.raw_name = price_readings.raw_name
          AND name_mappings.status = 'mapped'
    )
    WHERE product_id IS NULL
      AND EXISTS (
        SELECT 1 FROM name_mappings
        WHERE name_mappings.raw_name = price_readings.raw_name
          AND name_mappings.status = 'mapped'
      )
''').rowcount
conn.commit()
total = conn.execute('SELECT COUNT(*) FROM price_readings').fetchone()[0]
with_pid = conn.execute('SELECT COUNT(*) FROM price_readings WHERE product_id IS NOT NULL').fetchone()[0]
print(f'Backfilled {updated} rows. Total with product_id: {with_pid}/{total}')
conn.close()
\""
```

## Step 5 — report

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
stats = dict(conn.execute('SELECT status, COUNT(*) FROM name_mappings GROUP BY status').fetchall())
print('name_mappings:', stats)
pr = conn.execute('SELECT COUNT(*) FROM price_readings').fetchone()[0]
pr_pid = conn.execute('SELECT COUNT(*) FROM price_readings WHERE product_id IS NOT NULL').fetchone()[0]
print(f'price_readings with product_id: {pr_pid}/{pr}')
conn.close()
\""
```
