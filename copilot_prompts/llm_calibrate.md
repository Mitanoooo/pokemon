# Calibration Session — Claude Code prompt

Paste this prompt into a Claude Code session. It will fetch 25 high-frequency raw_names from Hetzner, walk through each one interactively with the operator, and write the results to `copilot_prompts/calibration_examples.md`.

---

Your task is to run a 25-product calibration session. You will present each raw_name and its top-5 curated-catalog candidates, wait for the operator to confirm or correct the mapping, and record their reasoning. At the end you will write the results to `copilot_prompts/calibration_examples.md`. Run this only after `update_catalog.py` has populated the curated catalog; the output file becomes the few-shot example bank for the batch normalisation prompt.

## Connection

```
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63
```

Database: `/opt/pokemon/pokemon.db`
Python: `/opt/pokemon/venv/bin/python`

## Step 1 — fetch raw_name candidates

Run this to get the raw_names you will calibrate, along with frequency and site info:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3, json
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
rows = conn.execute('''
    SELECT
        pr.raw_name,
        COUNT(*)                             AS reading_count,
        GROUP_CONCAT(DISTINCT s.name)        AS sites
    FROM price_readings pr
    JOIN sites s ON s.id = pr.site_id
    GROUP BY pr.raw_name
    ORDER BY reading_count DESC
    LIMIT 200
''').fetchall()
for r in rows:
    print(json.dumps({'raw_name': r[0], 'count': r[1], 'sites': r[2]}))
conn.close()
\""
```

From these 200 candidates, **select exactly 25 raw_names** using the following rule: pick the highest-frequency names overall, but ensure at least 1 raw_name from each of these three retailer clusters:

- **Large chains** — site names containing Prisma, Gigantti, Verkkokauppa, Toys, Lekia, or Stadium
- **Small hobby shops** — independent game/hobby store domains (short `.fi` domains, single-store names)
- **Swedish-language** — site names or URLs containing `.se`, `spelbutiken`, `webhallen`, `pokebutiken`, or `lekextra`

Hold the final 25 in memory — you will loop over them in Step 3.

## Step 2 — fetch the curated catalog

Load all curated products from Hetzner. You will use this list for candidate matching throughout the session.

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3, json
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
rows = conn.execute('''
    SELECT id, name, category_name, popularity_rank
    FROM cardmarket_products
    WHERE is_curated = 1
    ORDER BY popularity_rank ASC
''').fetchall()
for r in rows:
    print(json.dumps({'id': r[0], 'name': r[1], 'category': r[2], 'rank': r[3]}))
conn.close()
\""
```

## Step 3 — calibration loop

Work through the 25 raw_names **one at a time**. For each raw_name:

1. **Find top-5 candidates.** Using the curated catalog from Step 2, score each product with `difflib.SequenceMatcher(None, raw_name.lower(), product_name.lower()).ratio()`, then use `popularity_rank` as a tiebreaker (lower = more popular). Pick the 5 highest-scoring products.

   Note that `popularity_rank` is numbered **per category**, not globally — 8 different products sit at rank 1. It is a usable tiebreaker within a category but does not order the catalog as a whole, so do not read rank 1 as "most popular product overall".

2. **Present to the operator.** Display the following block and then **stop and wait for the operator to reply before proceeding**:

```
─────────────────────────────────────────────────────────────
Calibration [N/25]: <raw_name>
Sites: <comma-separated site names>

Candidates:
  1. <name> (ID: <id>)
  2. <name> (ID: <id>)
  3. <name> (ID: <id>)
  4. <name> (ID: <id>)
  5. <name> (ID: <id>)

Please provide:
  chosen_id  — the product ID that matches, or "none" if nothing fits
  why_match  — one sentence: why the chosen product matches (skip if "none")
  why_not    — for each of the 5 candidates, one short phrase explaining
               why it does NOT match (if you chose one of them, explain
               why the other 4 don't match)
─────────────────────────────────────────────────────────────
```

3. **Record the response.** Do not advance to the next raw_name until the operator has answered all fields.

Repeat until all 25 raw_names are done.

## Step 4 — write calibration_examples.md

After the operator confirms the last entry, write `copilot_prompts/calibration_examples.md` with this header followed by all 25 examples:

```markdown
# Calibration Examples

Generated during the calibration session (ticket 09). Used as few-shot examples
in the batch normalisation prompt (ticket 10).

Total: 25 examples
```

Use this format for each example:

```markdown
## Example N

**raw_name:** `<raw_name>`

**Candidates shown:**
1. <name> (ID: <id>)
2. <name> (ID: <id>)
3. <name> (ID: <id>)
4. <name> (ID: <id>)
5. <name> (ID: <id>)

**Chosen mapping:** <name> (ID: <id>) — or `none`

**Why it matched:** <operator's why_match text>

**Why candidates didn't match:**
- <candidate 1 name>: <operator's reason>
- <candidate 2 name>: <operator's reason>
- <candidate 3 name>: <operator's reason>
- <candidate 4 name>: <operator's reason>
- <candidate 5 name>: <operator's reason>
```
