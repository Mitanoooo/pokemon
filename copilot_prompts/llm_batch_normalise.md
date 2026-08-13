# Batch Normalization — Claude Code prompt

Paste this prompt into a Claude Code session. It supersedes `llm_normalise.md` as the primary normalization tool. It fetches every unprocessed raw_name from Hetzner, processes them in batches of 100 using the curated catalog and calibration examples, and outputs a verified CSV per batch that the operator feeds into `apply_batch.py`.

Run `llm_calibrate.md` and `update_catalog.py` before this prompt — the curated catalog and `calibration_examples.md` must exist first.

---

## Connection

```
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63
```

Database: `/opt/pokemon/pokemon.db`
Python: `/opt/pokemon/venv/bin/python`

---

## Step 1 — fetch all raw_names and their observed prices from Hetzner

Run this to retrieve every distinct raw_name that has ever appeared in `price_readings`, together with the price range it has been seen at and the sites that list it:

```bash
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 \
  "/opt/pokemon/venv/bin/python -c \"
import sqlite3, json
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
rows = conn.execute('''
    SELECT pr.raw_name,
           MIN(pr.price), MAX(pr.price), pr.currency,
           GROUP_CONCAT(DISTINCT s.name)
    FROM price_readings pr
    LEFT JOIN sites s ON s.id = pr.site_id
    GROUP BY pr.raw_name, pr.currency
    ORDER BY pr.raw_name
''').fetchall()
names = [{'raw_name': r[0], 'price_min': r[1], 'price_max': r[2],
          'currency': r[3], 'sites': r[4]} for r in rows]
print(json.dumps(names))
conn.close()
\""
```

Hold this list in memory as `all_remote_names`. Each entry carries the raw_name plus its observed price range — Step 5f uses the price to tell a single pack from a display box, which is the single most common mapping error.

Two quirks of this query's output, as of 2026-08-13:

- It returns **1,315 rows for 1,304 distinct raw_names**, because 11 names are listed in both EUR and SEK and the `GROUP BY` includes `currency`. Treat those as one name — process it once, and prefer the EUR row when reading its price.
- One raw_name is the **empty string** (2 readings, Fantasialinna). It carries no information at all, so it is `undecided` with an empty id under trigger (a).

---

## Step 2 — compute unprocessed names from local draft

Read `draft_mappings.json` from the project root. If the file does not exist, treat it as an empty list.

```bash
cat draft_mappings.json 2>/dev/null || echo "[]"
```

Parse the JSON array. Extract the `raw_name` field from every entry and hold that set as `already_processed`.

Compare on `raw_name` only — `all_remote_names` entries are objects now, so use `entry['raw_name']` when diffing.

Compute: `todo = all_remote_names - already_processed` (set difference, order preserved from `all_remote_names`).

Print a summary before continuing:

```
Remote raw_names:       <N>
Already in draft:       <N>
Remaining to process:   <N>
Batches to run:         <N>  (batches of 100)
```

If `todo` is empty, print "Nothing to do — all raw_names are already in draft_mappings.json." and stop.

---

## Step 3 — fetch the curated catalog from Hetzner

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
catalog = [{'id': r[0], 'name': r[1], 'category': r[2], 'rank': r[3]} for r in rows]
print(json.dumps(catalog))
conn.close()
\""
```

Hold this list in memory as `curated_catalog`. It is sorted by `popularity_rank` ASC — most popular products come first.

---

## Step 4 — read calibration examples

Read `copilot_prompts/calibration_examples.md` from the project root. Hold its full text in memory as `calibration_examples`. You will use it as few-shot context when assigning mappings in Step 6.

---

## Step 5 — normalization rules

Apply these rules consistently to every raw_name in every batch.

### 5a — Classification rule (in-scope vs. out-of-scope)

Only the following 8 Cardmarket product categories are in-scope for `mapped` status. The right-hand column is the literal `category` string on every `curated_catalog` entry — match on that, not on the prose label, and note that "Booster Boxes" is `Pokémon Display` and "Theme Decks" is singular:

| # | Category | `category` value in `curated_catalog` | Curated rows |
|---|---|---|---|
| 1 | Boosters | `Pokémon Booster` | 297 |
| 2 | Booster Boxes | `Pokémon Display` | 296 |
| 3 | Theme Decks | `Pokémon Theme Deck` | 297 |
| 4 | Trainer Kits | `Pokémon Trainer Kits` | 12 |
| 5 | Tins | `Pokémon Tins` | 297 |
| 6 | Box Sets | `Pokémon Box Set` | 295 |
| 7 | Elite Trainer Boxes | `Pokémon Elite Trainer Boxes` | 157 |
| 8 | Blisters | `Pokémon Blisters` | 297 |

Those eight are the whole curated catalog — 1,948 rows as of 2026-08-13 — so any product absent from `curated_catalog` is out of scope by construction.

Any raw_name that clearly does not refer to a product in one of these 8 categories must be `null_mapped`. This includes (but is not limited to):

- Individual cards / singles / promo cards (pattern: "Name – Set #NNN")
- Non-Pokémon TCG products (Lorcana, Magic: the Gathering, FIFA/Panini, Topps, One Piece, Digimon, Yu-Gi-Oh)
- Non-TCG products: toys, plush figures, costumes, puzzles, binders, sleeves, playmats, display stands, card storage, Funko POPs, LEGO, Mega Construx
- Gift sets and Pokémon Center exclusives whose category is not one of the 8 above

### 5b — Status definitions

| Status | When to assign | `cardmarket_product_id` |
|---|---|---|
| `mapped` | You are confident (≥ 0.85) this raw_name refers to a specific product in `curated_catalog` | Set to the matching product's `id` |
| `null_mapped` | You are confident this is not a sealed Pokémon TCG product from the 8 categories | `null` |
| `undecided` | Either (a) the text is garbled, too short to interpret, or in a completely unrecognized language, or (b) the product family is certain but the listing does not name the featured Pokémon and the catalog splits that family into per-Pokémon rows | Set to the best-guess product `id` if any plausible candidate exists, otherwise `null` |

**`undecided` is not a substitute for low confidence.** If you are uncertain which of two products a raw_name refers to, pick the more popular one and use `mapped` or `null_mapped` as appropriate.

The two `undecided` triggers are narrow and specific:

- **(a) Uninterpretable text.** Genuinely unreadable, not merely awkward. Mojibake affecting a character or two (`PokÃ©mon` for `Pokémon`) is mechanical damage, not uninterpretable — decode it and map normally. See calibration example 16.
- **(b) Unnamed variant.** Blisters, checklane blisters, mini tins and sticker collections are listed per featured Pokémon. When the set and product type are certain but the Pokémon is not stated, set `undecided` and record the lowest-`popularity_rank` variant as the best-guess id. See calibration examples 3, 4, 11 and 23. When the family has so many members that a guess is meaningless (e.g. 29 World Championship deck rows with no year or player named), leave the id empty — example 17.

### 5b2 — Operator decision rules

These come from the step-3 calibration session and are binding. `calibration_examples.md` works each one through in full.

| # | Situation | Rule | Example |
|---|---|---|---|
| 1 | Retailer ships "1 of N random selection" | `null_mapped` — no single row is the product sold | 5, 6, 12 |
| 2 | Product family certain, featured Pokémon unnamed | `undecided` + lowest-rank variant as best guess | 3, 4, 11, 23 |
| 3 | Retailer sells a multi-unit case (`Case (12)`, `Booster Box (6)`) | Map to the **single-unit** row | 11 |
| 4 | Catalog has both a plain and a Pokémon Center edition | Prefer the **plain** retail edition | 15 |
| 5 | Bare "Booster" / "Boosteri" / "Boosterpakkaus", no box qualifier | The single-pack `<Set> Booster` row | 2, 16, 19, 20, 21 |
| 6 | Listing sells a service, not a product ("BOX BREAK", "Rip & Ship") | `null_mapped` — the buyer receives loose cards | 9, 10 |

Rule 2 outranks rule 3: a case of an unnamed variant is `undecided`, and its best guess is the single-unit variant rather than the catalog's multi-unit "Display" row (example 11).

Rule 3 has a known, accepted consequence: a case price is 6–12× the single-unit price, so those readings will surface later as price outliers. Apply the rule anyway.

### 5c — Candidate selection and soft prior

When assessing a raw_name:

1. **Strip retailer noise first.** Search on what is left, not on the raw string. Noise seen in production: brand prefixes concatenated without separators (`PokémonScarlet & Violet 10: ...`), era prefixes that are not the set name (`Scarlet & Violet: Paradox Rift booster` — the set is Paradox Rift), un-decoded HTML entities (`&amp;`), release dates (`REL 17/7`), purchase limits (`MAX 1 kpl/asiakas`), and filler nouns (`Keräilykortit`). Set codes must be decoded: `ME01`–`ME05` are Mega Evolution / Phantasmal Flames / Perfect Order / Chaos Rising / Pitch Black; `SVn` numbers the Scarlet & Violet sets; Japanese sub-sets like `M5` (Abyss Eye) are named directly by Cardmarket, so match the sub-set and drop the umbrella name.
2. Search the **whole catalog**. Do not rank by string similarity and stop at the top few — a long retailer prefix pushes the correct row well down. In calibration examples 7, 8, 15, 19 and 25 the correct product is absent from the top five by `difflib` ratio entirely.
3. If two or more candidates are equally plausible, **prefer the one with the lower `popularity_rank`** (i.e., the more popular product). The catalog is already sorted by `popularity_rank` ASC, so earlier entries are preferred by default. This prior loses to any explicit product-type word in the listing — see 5f and example 22.
4. If no candidate is plausible and the raw_name clearly refers to an in-scope sealed product that is simply absent from the curated catalog, still assign `null_mapped` — do not force a low-confidence match to a wrong product.

### 5d — Finnish → English translation glossary

Finnish retailer listings often use Finnish or mixed-language product names. Use this glossary before searching for candidates:

| Finnish term | English equivalent |
|---|---|
| Boosterpakkaus / Boosteri | Booster (single pack) |
| Näyttölaatikko / Näyttö / Display | Booster Box / Display Box |
| ETB / Elite Trainer Box | Elite Trainer Box |
| Tin / Tinarasia | Tin |
| Paketti / Pakkaus | Pack / Bundle |
| Korttipeli | Card game |
| Aloituspakka / Aloituspakkaus | Starter Deck / Theme Deck |
| Blister / Blisterpakkaus | Blister pack |
| Lahjakortti / Lahjapaketti | Gift card / Gift set |
| Pelilauta / Pelimatto | Playmat → null_mapped |
| Suoja / Suojamuovi / Sleeves | Card sleeves → null_mapped |
| Kansio / Binder | Card binder → null_mapped |
| Figuuri / Pehmolelut | Figure / Plush → null_mapped |

Also seen in production: `laatikko` = box (so "Booster laatikko" is the display box, not the pack — example 22), `Keräilykortit` = trading cards (filler), `Keräilykansio` = collector binder (`null_mapped`), `Japaniksi` = in Japanese, `Yksinkertaistettu Kiina` = Simplified Chinese, `kpl` = pieces, `MAX 1 kpl/asiakas` = purchase limit (noise).

Swedish-language terms are similar to English; treat "Boosterpaket" as Booster, "Displaybox" as Booster Box, "Starterdäck" as Theme Deck. Note that in practice almost none of the tracked sites are Swedish-language — Finnish is the second language that actually appears.

### 5e — Calibration examples as few-shot context

The calibration examples in `calibration_examples.md` show 25 worked mappings with operator-supplied reasoning. Before assigning a mapping, check whether any calibration example has a similar raw_name or set name — use those decisions as a precedent for matching style and confidence thresholds.

Those 25 were chosen because a naive match gets them wrong. Every one encodes a rule from 5b2, so read the reasoning, not just the chosen ids.

### 5f — Observed price as a product-form discriminator

Every raw_name arrives from Step 1 with `price_min` / `price_max`. Use it to choose between product *forms* of the same set — this is where mapping most often goes wrong, because "Booster" alone appears in ~26% of tracked raw_names with no qualifier.

Rough bands observed in production. **They are EUR.** A small number of readings are SEK (11 raw_names, all also listed in EUR) — divide a SEK figure by roughly 11 before comparing it to the table, or just use that name's EUR reading:

| Observed price | Likely form |
|---|---|
| < 4 | Not a sealed product — a box-break or Rip & Ship slot (rule 6) |
| 4–12 | Single booster pack |
| 8–25 | Blister / checklane blister / mini tin |
| 25–60 | Booster bundle, ETB, tin, collector chest, League Battle Deck |
| 80–120 | Japanese or Chinese booster box |
| 150–400 | English 18- or 36-pack display box |
| > 500 | Multi-unit case — apply rule 3 and map to the single-unit row anyway |

**This is a prior, not a rule.** Heavily scalped sets break the bands upward: a single Prismatic Evolutions pack lists at 20.95 EUR (example 16) and a plain Phantasmal Flames ETB at 149.00 EUR (example 15), which alone would argue for a display box and a Pokémon Center edition respectively. When price and an explicit product-type word in the listing disagree, the listing text wins; when the listing is silent on form, price decides.

Two useful sanity checks it does catch: a "Booster" at 389.50 EUR is a display box (example 22), and a "Booster Box" at 199.90 EUR is the standard 36-pack rather than the 18-pack variant (example 24).

---

## Step 6 — batch loop

Split `todo` into batches of 100 (the final batch may be smaller).

For each batch:

### 6a — Assess all 100 names

Work through the 100 raw_names in order. For each one, apply the rules in Step 5 and produce:

| Field | Description |
|---|---|
| `raw_name` | Exact value as fetched from the DB — do not alter |
| `proposed_name` | The matched product name from `curated_catalog`, or empty string if `null_mapped` / `undecided` |
| `cardmarket_product_id` | Integer product ID, or empty if `null_mapped` / no plausible match for `undecided` |
| `confidence` | Float 0.00–1.00 (two decimal places). Use ≥ 0.85 for `mapped` and `null_mapped`; use < 0.85 only for `undecided` |
| `status` | `mapped`, `null_mapped`, or `undecided` |
| `observed_price` | The `price_max` from Step 1, two decimal places, no currency symbol. Review-only — carry it through so the operator can spot a pack/box mix-up at a glance |

### 6b — Write the batch CSV

Write the results to a file named `batch_NNN.csv` where NNN is the zero-padded batch number (e.g. `batch_001.csv`, `batch_002.csv`). Use the working directory of the project root.

CSV format:
```
raw_name,proposed_name,cardmarket_product_id,confidence,status,observed_price
```

No quoting is necessary unless the value contains a comma or newline. Use UTF-8 encoding.

`observed_price` is the last column and exists purely for the operator's review pass. `apply_batch.py` reads the CSV with `csv.DictReader` and pulls named fields, so the extra column is ignored on the way into `draft_mappings.json` — no script change is needed.

After writing the file, print:

```
Batch NNN written to batch_NNN.csv
  mapped:      <N>
  null_mapped: <N>
  undecided:   <N>
  ─────────────────────────────────
  Total:       <N>
```

### 6c — Pause for operator review

After printing the summary, **stop and wait for the operator to reply before processing the next batch.**

Display this prompt to the operator:

```
─────────────────────────────────────────────────────────────
Operator review — batch_NNN.csv

Open the file in a spreadsheet tool or text editor.
Correct rows need no action.

Quickest check: sort by observed_price and scan for a "Booster"
mapped at 200+ EUR, or a "Booster Box" mapped at under 20 EUR.

For incorrect rows, either:
  (a) Edit the CSV directly and save it, then reply: done
  (b) Reply: skip  — to discard this batch and re-run it

After review, run:
  python scripts/apply_batch.py batch_NNN.csv

Then reply "next" to continue with the next batch, or "stop" to end the session.
─────────────────────────────────────────────────────────────
```

Wait for the operator's reply. If the operator replies:
- `next` or `done` — proceed to the next batch
- `stop` — end the session and print the final summary (see Step 7)
- `skip` — discard the current batch CSV and re-run the same 100 names

Do not advance automatically. Only proceed when the operator explicitly replies.

---

## Step 7 — session summary

When all batches are complete (or the operator replies `stop`), print:

```
─────────────────────────────────────────────────────────────
Session complete.

Batches written:   <N>
Raw names covered: <N>  (this session)
Remaining in todo: <N>  (re-run this prompt to continue)

Next steps:
  1. Run apply_batch.py for any batches not yet accumulated.
  2. Once all batches are verified, run:
       python scripts/apply_batch.py --finalize
     to push the full draft_mappings.json to production.
─────────────────────────────────────────────────────────────
```
