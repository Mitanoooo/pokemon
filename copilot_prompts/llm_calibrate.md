# Calibration Session — Claude Code prompt

Paste this prompt into a Claude Code session. It will select 25 hard-to-match raw_names from Hetzner, walk through each one interactively with the operator, and write the results to `copilot_prompts/calibration_examples.md`.

---

Your task is to run a 25-product calibration session. You will present each raw_name and its top-5 curated-catalog candidates, wait for the operator to confirm or correct the mapping (the answer is often none of the five — see Step 3), and record their reasoning. At the end you will write the results to `copilot_prompts/calibration_examples.md`. Run this only after `update_catalog.py` has populated the curated catalog; the output file becomes the few-shot example bank for the batch normalisation prompt.

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
''').fetchall()
for r in rows:
    print(json.dumps({'raw_name': r[0], 'count': r[1], 'sites': r[2]}))
conn.close()
\""
```

**Select exactly 25 raw_names — by difficulty, not by frequency.** Consider all of them; the query orders by frequency only to show the distribution, and deliberately has no `LIMIT`.

> **Amended 2026-08-13 after the first real run (ticket 12, step 3).** The original rule here was "pick the highest-frequency names, with at least one from large chains / small hobby shops / Swedish-language sites". It does not survive contact with the data and produced a useless first selection:
>
> - **Frequency is flat.** Of 1,304 distinct raw_names, 1 has 8 readings, 2 have 6, 28 have 4, 1,172 have exactly 2 and 99 have 1. `ORDER BY reading_count DESC LIMIT 200` returns ~33 genuinely frequent names and 167 whose position is SQLite's tie order — in practice an alphabetical run dominated by a single site.
> - **There is no Swedish-language cluster.** One tracked site is `.se` and its listings are in English. The second language that actually appears is Finnish.
> - **High-frequency names are disproportionately easy.** 54 of the 1,304 are exact matches for a catalog name. An example whose answer is a 1:1 string match teaches nothing.

Select for cases where a naive match is *wrong*. Aim for a spread across these, which is what the shipped bank covers:

- Retailer set codes standing in for a set name (`ME05`, `SV6`, `M5`, `CBB4C`)
- A long retailer prefix that outscores the set name (era prefixes, concatenated brand names, `&amp;`)
- Word-order inversion vs. the catalog (`Elite Trainer Box Phantasmal Flames`, `Collector's Chest Fall 2025`)
- Finnish product-type words (`boosteri`, `laatikko`, `boosterpakkaus`, `keräilykansio`)
- Mojibake (`PokÃ©mon`) — mechanical damage, still mappable
- Random assortments (`1 of 2 random selection`) and services (`BOX BREAK`, `Rip & Ship`)
- Multi-unit cases (`Case (12)`, `Booster Box (6)`)
- Product families the catalog splits per featured Pokémon, where the listing names none
- Out-of-scope items that read like in-scope ones (Ultra Pro deck boxes, binders, Topps F1)

Fetch each selected name's observed price as well — it is the decisive pack-vs-box signal and belongs in the recorded example:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3, json
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
for r in conn.execute('''
    SELECT raw_name, MIN(price), MAX(price), currency
    FROM price_readings GROUP BY raw_name, currency
'''):
    print(json.dumps({'raw_name': r[0], 'min': r[1], 'max': r[2], 'currency': r[3]}, ensure_ascii=False))
conn.close()
\""
```

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

   `scripts/calibration_candidates.py` implements exactly this rule; use it rather than re-deriving the scoring:

   ```bash
   python scripts/calibration_candidates.py /tmp/curated.jsonl --file names.tsv
   ```

   **The top 5 frequently does not contain the right answer.** The ratio is whole-string, so a long retailer prefix outweighs the set name — for `Scarlet &amp; Violet: Paradox Rift booster` every one of the five is a Scarlet & Violet base-set row and `Paradox Rift Booster` is absent. Ten of the 25 shipped examples were like this. The script prints a second token-overlap list below the top 5 for exactly this reason; tell the operator they may name **any** product id, not just 1–5.

2. **Present to the operator.** Display the following block and then **stop and wait for the operator to reply before proceeding**:

```
─────────────────────────────────────────────────────────────
Calibration [N/25]: <raw_name>
Sites: <comma-separated site names>

Observed price: <min>–<max> <currency>

Candidates:
  1. <name> (ID: <id>)  [<category>, rank <n>, score <s>]
  2. <name> (ID: <id>)  [<category>, rank <n>, score <s>]
  3. <name> (ID: <id>)  [<category>, rank <n>, score <s>]
  4. <name> (ID: <id>)  [<category>, rank <n>, score <s>]
  5. <name> (ID: <id>)  [<category>, rank <n>, score <s>]

Also in catalog (token overlap, not part of the top-5):
   - <name> (ID: <id>)  [<category>, rank <n>, cov <c>]

Please provide:
  chosen_id  — the product ID that matches, or "none" if nothing fits.
               Any id in the catalog is valid, not just 1–5.
  status     — mapped | null_mapped | undecided
  why_match  — one sentence: why the chosen product matches (skip if "none")
  why_not    — for each of the 5 candidates, one short phrase explaining
               why it does NOT match (if you chose one of them, explain
               why the other 4 don't match)
─────────────────────────────────────────────────────────────
```

`status` distinguishes the two reasons a `chosen_id` may be absent, and marks a best guess as a guess:

| Status | Meaning | `chosen_id` |
|---|---|---|
| `mapped` | Confident match | the product id |
| `null_mapped` | Confidently not a sealed in-scope product | `none` |
| `undecided` | Uninterpretable text, or the family is certain but the featured Pokémon is unnamed | best-guess id, or `none` if a guess would be meaningless |

The operator may answer tersely (`1, match, names match exactly`). Draft the missing `why_not` phrases yourself and ask them to correct what you got wrong rather than blocking on all seven fields.

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

**Sites:** <sites>  ·  **Observed price:** <price> <currency>

**Candidates shown:**
1. <name> (ID: <id>) — <category>, rank <n>, score <s>
2. <name> (ID: <id>) — <category>, rank <n>, score <s>
3. <name> (ID: <id>) — <category>, rank <n>, score <s>
4. <name> (ID: <id>) — <category>, rank <n>, score <s>
5. <name> (ID: <id>) — <category>, rank <n>, score <s>

**Chosen mapping:** <name> (ID: <id>) — or `none`

**Status:** `mapped` | `null_mapped` | `undecided`

**Why it matched:** <operator's why_match text>

**Why candidates didn't match:**
- <candidate 1 name>: <operator's reason>
- <candidate 2 name>: <operator's reason>
- <candidate 3 name>: <operator's reason>
- <candidate 4 name>: <operator's reason>
- <candidate 5 name>: <operator's reason>
```

Give one reason line per candidate shown, including the chosen one (write "this is the chosen row" for it) so the list always has five entries.

Also record, above Example 1:

- **How the bank was selected** — so a later reader does not assume it is a frequency sample.
- **The operator's decision rules**, as a numbered table with the example numbers that demonstrate each. These are the part `llm_batch_normalise.md` § 5b2 mirrors; the worked examples are only evidence for them.
- **Any rule precedence** the session established (e.g. an unnamed variant sold as a case is `undecided`, not a case-mapping).

`tests/test_calibration_examples.py` asserts this structure — run it after writing the file.
