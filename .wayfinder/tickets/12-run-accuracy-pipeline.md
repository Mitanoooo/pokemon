# 12 — Run the accuracy pipeline

## Question

Execute the full accuracy overhaul pipeline end-to-end:

1. Run `scrape_catalog.md` in Copilot (operator passes captcha); save the output JSON file
2. Run `update_catalog.py` with the output file; verify matched count is reasonable
3. Run `llm_calibrate.md` in a Claude Code session; complete the 25-product calibration; confirm `calibration_examples.md` is written
4. Run `llm_batch_normalise.md` in batches of 100; review each CSV; annotate incorrect rows; run `apply_batch.py` after each verified batch
5. Once all batches are done, run `apply_batch.py --finalize`
6. Report final `name_mappings` counts (mapped / null_mapped / undecided) and `price_readings` backfill count

**Status: OPEN — steps 1–3 done 2026-08-13, steps 4–6 remain.** All four blockers (08, 09, 10, 11) are closed. Mostly execution, but step 3 forced two prompt amendments (see Progress).

Blocked by: 08, 09, 10, 11 — all closed

### Progress

- **Step 1 done (2026-08-13), with a deviation.** The browser session saved 8 plain-text dumps in the project root (`catalog_boosters.txt`, `catalog_booster_boxes.txt`, …) instead of one `catalog_scrape.json`. Each line is a link label plus a product URL; the listing pages never exposed the integer product id, so the dumps carry no `cardmarket_product_id` at all.
  - `scripts/extract_catalog.py` (new) converts the dumps to `catalog_scrape.json` in the ticket-07 schema, recovering ids by joining each product's URL slug to `cardmarket_catalogue.json`. See "Step 1a" below.
  - Result: **1,960 products, 1,948 with ids, 12 null.** Passes the step-1 sanity check.
- **Step 2 done (2026-08-13).** `matched: 1948`, `not_found: 0`. Verified on Hetzner: 1,948 rows at `is_curated=1`, ranks 1–300, popularity order intact (Boosters rank 1 = "Destined Rivals Booster").
  - `not_found: 0` means the base catalogue did **not** need re-importing — every resolvable product was already in the 5,006-row import.
- **Step 3 done (2026-08-13), with three deviations.** `copilot_prompts/calibration_examples.md` now exists: 25 worked examples, **12 `mapped` / 8 `null_mapped` / 5 `undecided`**. Every product id in it was verified to resolve to a real `is_curated = 1` row.
  - **The prompt's selection rule was unusable, so examples were picked by difficulty instead.** Reading counts are almost flat — of 1,304 distinct raw_names, 1 has 8 readings, 2 have 6, 28 have 4, 1,172 have exactly 2, and 99 have 1. The prompt's "top 200 by frequency" therefore returns ~33 genuinely frequent names plus 167 arbitrary tie-ordered ones, and SQLite's tie order handed back an alphabetical MaxGaming-dominated run. 54 of those names are also exact string matches that teach nothing. The 25 were instead chosen so that a naive top-1 match is wrong or genuine ambiguity exists.
  - **The prompt's "Swedish-language sites" stratum barely exists.** Only one tracked site is `.se` and its listings are in English; Finnish is the second language that actually appears. The bank is weighted to Finnish accordingly.
  - **The output format gained a `Status:` field per example.** The calibration produced a three-way `mapped` / `null_mapped` / `undecided` decision, which the format in `llm_calibrate.md` has no field for. Observed price and listing sites are recorded per example too, since price turned out to be the decisive pack-vs-box signal.
- **Step 3 produced six binding operator rules**, all worked through in the examples file and mirrored into `llm_batch_normalise.md` § 5b2: random-assortment listings → `null_mapped`; unnamed featured Pokémon → `undecided` + lowest-rank best guess; multi-unit cases → the single-unit row; plain edition preferred over Pokémon Center; bare "Booster" → the single-pack row; box-break / Rip & Ship services → `null_mapped`.
- **`llm_batch_normalise.md` amended for step 4 (2026-08-13).** Step 1 now fetches each raw_name's observed price range and sites alongside the name, and a new § 5f uses price to separate product forms — single packs read 4–12 EUR against 150–400 EUR for display boxes, and 26% of tracked raw_names are a bare "Booster"/"Boosteri" with no qualifier. Batch CSVs gain a trailing review-only `observed_price` column; `apply_batch.py` needs no change because `csv.DictReader` pulls named fields (now covered by `tests/test_apply_batch.py`). § 5a also gained the literal `category` strings, since "Booster Boxes" is `Pokémon Display` in the data and "Theme Decks" is singular.
  - Price is a **prior, not a rule** — scalped sets break the bands upward. A single Prismatic Evolutions pack lists at 20.95 EUR and a plain Phantasmal Flames ETB at 149.00 EUR, which on price alone would read as a box and a Pokémon Center edition respectively. Both are recorded in the bank as counter-examples.
- **Two data quirks step 4 will hit.** The step-1 query returns **1,315 rows for 1,304 distinct raw_names** (11 names are listed in both EUR and SEK and the `GROUP BY` includes currency — treat them as one name, prefer the EUR row), and one raw_name is the **empty string** (2 readings, Fantasialinna).
- **`scripts/calibration_candidates.py` (new) ships with the pipeline.** It implements the prompt's fixed scoring rule (`difflib` ratio, `popularity_rank` ASC tiebreaker) plus a token-overlap hint list, because the whole-string ratio genuinely excludes the correct product for some names — see the step-3 note below.
- **Steps 4–6 remain.** All are operator-interactive or destructive; see the runbook.

**Current production mapping state (2026-08-13), for the step-5 diff:** 1,280 mapped / 302 null_mapped / 235 undecided (1,817 rows; 1,911 `price_readings` linked; 1,304 distinct raw_names). This is *not* the ticket-05 state its step-5 text quotes — a later LLM pass has run since.

These rows are all LLM output and confirmed by the operator to be largely wrong; that inaccuracy is the reason this overhaul exists. Nothing here is hand-curated, so `--finalize` replacing all 1,817 wholesale is the intended outcome, not a loss. Still take the server-side DB copy first — there is no built-in undo if a *draft* turns out bad.

---

## Runbook

Artefacts that must exist when this is done: `catalog_scrape.json`, `copilot_prompts/calibration_examples.md`, `draft_mappings.json`, `batch_NNN.csv` files. `catalog_scrape.json` now exists; the rest do not.

Production `name_mappings` on Hetzner is untouched until step 5. Everything before that is local or catalog-only.

### Step 1 — scrape the catalog *(operator-driven, ~30–60 min)*

Paste `copilot_prompts/scrape_catalog.md` into a Copilot agentic browser session. Sit with it: a captcha appears at the start and may reappear mid-scrape, and the prompt is written to stop and wait each time. It walks 8 category pages × up to 10 pages each (~2,400 products) and writes `catalog_scrape.json` to the project root.

Sanity check before moving on: total near 2,000+, and the null-`cardmarket_product_id` count in the summary is small. A high null count means the listing markup changed and the id-extraction fallbacks in the prompt need revisiting — the nulls get silently dropped by step 2.

### Step 1a — recover product ids from the dumps *(automated, seconds)*

Only needed when the scrape lands as `catalog_<category>.txt` dumps rather than JSON — which is what happened on the 2026-08-13 run, and is the likely outcome whenever the browser agent can't see product ids in the listing markup.

```bash
python scripts/extract_catalog.py          # dumps in cwd -> catalog_scrape.json
```

Cardmarket's product URL slug is derived from the product name, but drops some punctuation outright (`McDonald's` → `McDonalds`, `CSV9.5C` → `CSV95C`) while turning other runs into hyphens. The script folds both the slug and each `cardmarket_catalogue.json` name down to bare lowercase alphanumerics, then joins on `(id_category, folded name)`. That resolved 1,942 / 1,960 (99.0%) on the first run.

**The slug is not always usable, so the listing label is the fallback.** Six products on the 2026-08-13 run had a slug that no fold can bridge — it omitted a word (`Poke-Ball-Tin` for "Generic Poké Ball Tin", `Regieleki-V-Collection` for "Crown Zenith: Regieleki V Collection"), dropped diacritics instead of transliterating them (`Ondej` for "Ondřej"), or was outright broken (`LocExpansionName-Blitzle-1-Pack-Blister`, a Cardmarket templating bug). Listing labels are expansion name + product name, so the real catalogue name is a trailing run of the label's words; the script tries the longest such suffix first, down to a floor of two words. One-word suffixes are refused because the catalogue genuinely contains rows named just "Booster". Every rescue is printed under "Resolved via listing label" — a short list, worth eyeballing since it is the one heuristic step in an otherwise exact join.

Three things the script handles that are worth knowing about:

- **Page-boundary repeats.** Several dumps repeat the last product of page N as the first of page N+1. Repeats are dropped so `popularity_rank` stays contiguous, but it means the scrape genuinely *missed* one product per overlap. Ranks are therefore approximate to within a few positions — fine for ordering, not exact.
- **Fold collisions.** The catalogue has a handful of same-named products under one category (e.g. two `Golisopod Stage 1 Blister` rows). These resolve to the lowest `idProduct` and are counted in the summary as `Ambiguous`. One occurred on the 2026-08-13 run.

The 12 remaining unresolved slugs are printed by name and are genuinely absent from the 2026-08-10 catalogue export. Cross-checked against all 1,304 tracked `raw_names` on 2026-08-13, only two of them are products we actually collect prices for:

| Unresolved product | Tracked as | Site |
|---|---|---|
| `CBB1C: Gem Pack Vol. 1` Booster + Booster Box | "PokémonGem Pack Vol 1 Booster Box (Simplified Chinese)" (2 readings) | MaxGaming |
| `WCD 2025: Riley McKay "Flutter Devo Gardevoir"` | "Pokémon TCG World Championships Deck 2025 – Riley McKay" (2 readings) | Pelimies |

The other ten have no tracked raw_name, so they cost nothing by staying uncurated. These two will `null_map` in step 4 despite being real sealed products. Two readings each is negligible, so it is reasonable to proceed and pick them up at the next quarterly re-scrape; re-exporting `cardmarket_catalogue.json` and re-running steps 1a–2 would fix them now if wanted.

### Step 2 — apply to the DB *(automated, seconds)*

```bash
python scripts/update_catalog.py catalog_scrape.json
```

Verify `matched` is in the low thousands and `not_found` is small. `not_found` = products on Cardmarket now but absent from the 5,006-row `cardmarket_catalogue.json` import — i.e. sets released since that JSON was captured. A large `not_found` means the base catalogue needs re-importing before calibration, since those products can never be matched.

Note this command wipes existing curation first, so the curated set always reflects the newest scrape only.

### Step 3 — calibration *(interactive, 25 answers, ~45–90 min)* — **DONE 2026-08-13**

Paste `copilot_prompts/llm_calibrate.md` into a Claude Code session. It loops: shows 5 candidates, waits for `chosen_id`, `why_match`, and a `why_not` phrase per rejected candidate. Output: `copilot_prompts/calibration_examples.md`.

This is the quality-determining step — the reasoning text becomes the few-shot bank that steers all ~1,300 mappings. Spend real effort on the `why_not` phrases; they teach the distinctions that matter (booster pack vs. booster box, set-name collisions, language variants).

**Ignore the prompt's selection rule if this is ever re-run.** "25 high-frequency raw_names stratified across large chains / small hobby shops / Swedish-language sites" does not survive contact with the data: reading counts are flat (1,172 of 1,304 names have exactly 2), so `ORDER BY COUNT(*) DESC LIMIT 200` is mostly tie-order noise, and there is effectively no Swedish-language stratum. Select for **difficulty** instead — names where the naive top-1 match is wrong. Exact string matches make useless examples; 54 of the 1,304 names are exact matches and none of them belong in the bank.

Generate the candidate lists with:

```bash
# dump the curated catalog once
ssh -i ~/.ssh/pokemon-hetzner root@65.21.178.63 "/opt/pokemon/venv/bin/python -c \"
import sqlite3, json
c = sqlite3.connect('/opt/pokemon/pokemon.db')
for r in c.execute('SELECT id, name, category_name, popularity_rank FROM cardmarket_products WHERE is_curated = 1'):
    print(json.dumps({'id': r[0], 'name': r[1], 'category': r[2], 'rank': r[3]}, ensure_ascii=False))
\"" > /tmp/curated.jsonl

python scripts/calibration_candidates.py /tmp/curated.jsonl --file names.tsv
```

**The top 5 does not always contain the right answer, so let the operator name any id.** The scoring rule the prompt fixes is a whole-string `difflib` ratio, and a long retailer prefix outweighs the set name — for `Scarlet &amp; Violet: Paradox Rift booster` all five candidates are Scarlet & Violet base-set rows and `Paradox Rift Booster` is absent. `calibration_candidates.py` prints a second token-overlap list below the top 5 to recover those cases; five of the 25 examples needed it.

Fetch each candidate name's observed price too — it is the decisive pack-vs-box signal and is now part of the recorded examples.

### Step 4 — batch normalisation *(interactive, ~13 batches, longest step)*

Paste `copilot_prompts/llm_batch_normalise.md` into a Claude Code session. Per batch of 100 it writes `batch_NNN.csv` then stops. For each batch:

1. Open the CSV; edit only the wrong rows (correct rows need no action)
2. `python scripts/apply_batch.py batch_NNN.csv`
3. Reply `next`

Quickest review pass: sort on the trailing `observed_price` column and look for a "Booster" mapped at 200+ EUR or a "Booster Box" mapped under 20 EUR. That column is review-only — `apply_batch.py` ignores it.

Also available at the pause: `skip` re-runs the same 100 names, `stop` ends the session. Safe to stop and resume across days — step 2 of the prompt diffs remote raw_names against `draft_mappings.json`, so a fresh session picks up exactly where the last one left off. With ~1,296 distinct raw_names, expect ~13 batches.

Accumulate mode is keyed on `raw_name`, so re-running a corrected CSV overwrites cleanly.

### Step 5 — finalize *(one destructive command)*

```bash
python scripts/apply_batch.py --finalize
```

Single transaction on Hetzner: `DELETE FROM name_mappings` → bulk INSERT the whole draft → backfill `price_readings.product_id`. This discards whatever is in `name_mappings` and replaces it wholesale — as of 2026-08-13 that is 1,817 rows of superseded LLM output (see "Progress" above), which is intended.

Only run this once every batch is accumulated. Check `draft_mappings.json` has ~1,296 entries first — finalizing a partial draft leaves every unprocessed raw_name with no mapping row at all.

Consider a DB copy on the server beforehand; there is no built-in undo.

### Step 6 — report

Record final `name_mappings` counts by status and the backfill count in this ticket's resolution. Caveat: the printed "Backfilled: N price_readings rows" counts rows touched, not rows linked (see ticket 11's known wart) — for the real number, query `SELECT COUNT(*) FROM price_readings WHERE product_id IS NOT NULL`.

Then check the Mapping Review UI (`app/views/mappings.py`) for the residual `undecided` queue — it should be far smaller than the previous 728, since `undecided` is now reserved for uninterpretable text rather than low confidence.
