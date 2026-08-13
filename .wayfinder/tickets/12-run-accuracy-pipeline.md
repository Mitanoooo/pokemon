# 12 — Run the accuracy pipeline

## Question

Execute the full accuracy overhaul pipeline end-to-end:

1. Run `scrape_catalog.md` in Copilot (operator passes captcha); save the output JSON file
2. Run `update_catalog.py` with the output file; verify matched count is reasonable
3. Run `llm_calibrate.md` in a Claude Code session; complete the 25-product calibration; confirm `calibration_examples.md` is written
4. Run `llm_batch_normalise.md` in batches of 100; review each CSV; annotate incorrect rows; run `apply_batch.py` after each verified batch
5. Once all batches are done, run `apply_batch.py --finalize`
6. Report final `name_mappings` counts (mapped / null_mapped / undecided) and `price_readings` backfill count

**Status: CLOSED — all six steps done 2026-08-13.** All four blockers (08, 09, 10, 11) were closed. Mostly execution, but step 3 forced two prompt amendments and step 4 amended rule 3 (see Progress). Final counts in Resolution below.

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
- **`llm_batch_normalise.md` amended for step 4 (2026-08-13).** Step 1 now fetches each raw_name's observed price range and sites alongside the name, and a new § 5f uses price to separate product forms — single packs read 4.90–7.29 EUR against 199.90–389.50 EUR for display boxes, and 26% of tracked raw_names are a bare "Booster"/"Boosteri" with no qualifier. § 5f is written form → price and read as an **exclusion filter**: the observed ranges overlap (80.00 EUR is an ETB *and* inside the Japanese-box range), so only "price below a form's floor rules that form out" is sound. Batch CSVs gain a trailing review-only `observed_price` column; `apply_batch.py` needs no change because `csv.DictReader` pulls named fields (now covered by `tests/test_apply_batch.py`). § 5a also gained the literal `category` strings, since "Booster Boxes" is `Pokémon Display` in the data and "Theme Decks" is singular.
  - Price is a **prior, not a rule** — scalped sets break the bands upward. A single Prismatic Evolutions pack lists at 20.95 EUR and a plain Phantasmal Flames ETB at 149.00 EUR, which on price alone would read as a box and a Pokémon Center edition respectively. Both are recorded in the bank as counter-examples.
- **Two data quirks step 4 will hit.** The step-1 query returns **1,315 rows for 1,304 distinct raw_names** (11 names are listed in both EUR and SEK and the `GROUP BY` includes currency — treat them as one name, prefer the EUR row), and one raw_name is the **empty string** (2 readings, Fantasialinna).
- **`scripts/calibration_candidates.py` (new) ships with the pipeline.** It implements the prompt's fixed scoring rule (`difflib` ratio, `popularity_rank` ASC tiebreaker) plus a token-overlap hint list, because the whole-string ratio genuinely excludes the correct product for some names — see the step-3 note below.
- **Step 3 reviewed (2026-08-13) and the review's findings applied.** The hint list had four real defects that steered it wrong: `Pokémon` tokenized to `pok`/`mon` (no accent folding, so every catalog row got two free tokens of overlap), the 2-char codes `m2`/`m5` expanded an Ultra Pro deck box into "Inferno X Booster", `box`/`pack` were treated as noise so pack-vs-box collapsed, and `me025` was unreachable dead code. All fixed with regression tests. On the docs side: the examples file was missing rule 6 from its table, § 5f's price table contradicted its own cited examples, and "five of the 25" off-top-5 was actually **ten** (1, 2, 3, 7, 8, 15, 19, 20, 23, 25) — now asserted by a test that recomputes it from the bank.
- **Step 4 done (2026-08-13).** All 14 batches written and accumulated; `draft_mappings.json` holds 1,304 entries, one per distinct remote raw_name, and the local draft/remote diff is empty in both directions. `batch_014.csv` (the final 4 names) had been written but not accumulated — the last run stopped between the write and the `apply_batch.py` call, which the step-2 diff caught on resume exactly as designed.
  - Draft validated before finalize: 0 `mapped` rows with a null id, 0 `null_mapped` rows carrying an id, 0 rows outside the three statuses, no missing confidences, every `mapped`/`null_mapped` at ≥ 0.85 and every `undecided` below it. All 348 distinct product ids resolve to real `is_curated = 1` rows.
  - 348 distinct ids across 831 id-bearing rows is heavy reuse and is correct: one product collects up to 20 retailer spellings (`885547 Pitch Black Booster` covers "Mega Evolution Pitch Black (ME05)", "Poke ME05 Booster REL 17/7", "Pitch Black Boosteri", …). Collapsing those variants is the point of the table.
- **Step 5 done (2026-08-13).** Backup first, then one `--finalize` run: 1,817 old rows deleted, 1,304 inserted, `price_readings.product_id` backfilled.
  - **A plain `cp` of `pokemon.db` is not a valid backup on this server.** The DB is in WAL mode and the WAL was 993 KB at the time — a file copy of the `.db` alone silently omits it. The backup was retaken with SQLite's `src.backup(dst)` API and verified (1,817 `name_mappings`, 2,581 `price_readings`, 1,911 linked, `integrity_check` = ok) at `/opt/pokemon/pokemon.db.pre-ticket12-finalize`. Use the backup API, not `cp`, for any future restore point here.
- **Step 6 done (2026-08-13).** Counts and the UI queue check are in Resolution below.

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

**The top 5 does not always contain the right answer, so let the operator name any id.** The scoring rule the prompt fixes is a whole-string `difflib` ratio, and a long retailer prefix outweighs the set name — for `Scarlet &amp; Violet: Paradox Rift booster` all five candidates are Scarlet & Violet base-set rows and `Paradox Rift Booster` is absent. `calibration_candidates.py` prints a second token-overlap list below the top 5 to recover those cases; ten of the 25 examples needed it.

Fetch each candidate name's observed price too — it is the decisive pack-vs-box signal and is now part of the recorded examples.

### Step 4 — batch normalisation *(interactive, 14 batches, longest step)*

Paste `copilot_prompts/llm_batch_normalise.md` into a Claude Code session. Per batch of 100 it writes `batch_NNN.csv` then stops. For each batch:

1. Open the CSV; edit only the wrong rows (correct rows need no action)
2. `python scripts/apply_batch.py batch_NNN.csv`
3. Reply `next`

Quickest review pass: sort on the trailing `observed_price` column and look for a "Booster" mapped at 200+ EUR or a "Booster Box" mapped under 20 EUR. That column is review-only — `apply_batch.py` ignores it.

Also available at the pause: `skip` re-runs the same 100 names, `stop` ends the session. Safe to stop and resume across days — step 2 of the prompt diffs remote raw_names against `draft_mappings.json`, so a fresh session picks up exactly where the last one left off. With 1,304 distinct raw_names, expect 14 batches (13 full plus a final batch of 4).

Accumulate mode is keyed on `raw_name`, so re-running a corrected CSV overwrites cleanly.

### Step 5 — finalize *(one destructive command)*

```bash
python scripts/apply_batch.py --finalize
```

Single transaction on Hetzner: `DELETE FROM name_mappings` → bulk INSERT the whole draft → backfill `price_readings.product_id`. This discards whatever is in `name_mappings` and replaces it wholesale — as of 2026-08-13 that is 1,817 rows of superseded LLM output (see "Progress" above), which is intended.

Only run this once every batch is accumulated. Check `draft_mappings.json` has 1,304 entries first (one per distinct raw_name as of 2026-08-13 — re-count with the step-1 query if readings have been scraped since) — finalizing a partial draft leaves every unprocessed raw_name with no mapping row at all.

Consider a DB copy on the server beforehand; there is no built-in undo.

### Step 6 — report

Record final `name_mappings` counts by status and the backfill count in this ticket's resolution. Caveat: the printed "Backfilled: N price_readings rows" counts rows touched, not rows linked (see ticket 11's known wart) — for the real number, query `SELECT COUNT(*) FROM price_readings WHERE product_id IS NOT NULL`.

Then check the Mapping Review UI (`app/views/mappings.py`) for the residual `undecided` queue — it should be far smaller than the previous 728, since `undecided` is now reserved for uninterpretable text rather than low confidence.

---

## Resolution *(2026-08-13)*

### Final `name_mappings` — 1,304 rows, one per distinct raw_name

| Status | Before | After | Δ |
|---|---|---|---|
| `mapped` | 1,280 | **726** | −554 |
| `null_mapped` | 302 | **468** | +166 |
| `undecided` | 235 | **110** | −125 |
| **Total** | 1,817 | **1,304** | −513 |

The 1,817 → 1,304 drop is not data loss: the old table had accumulated multiple rows per raw_name across successive LLM passes, and the new one is exactly one row per distinct raw_name.

### `price_readings` backfill

| Metric | Before | After |
|---|---|---|
| Total readings | 2,581 | 2,581 |
| **Linked (`product_id IS NOT NULL`)** | 1,911 | **1,426** |
| Unlinked | 670 | 1,155 |

`apply_batch.py` printed "Backfilled: 2581" — that is rows *touched* (the `UPDATE` has no `WHERE`, so it rewrites every row, ticket 11's known wart). The real linked figure is **1,426**, from `SELECT COUNT(*) FROM price_readings WHERE product_id IS NOT NULL`.

**Linked count went down by 485, and that is the overhaul working.** Those readings were previously linked to *wrong* products. `null_mapped` nearly doubled because the old pass force-matched non-TCG junk, singles, box-break services and random-assortment listings onto real sealed products; each of those now correctly resolves to no product. A reading count of 1,426 that is right beats 1,911 where a large share pointed at the wrong SKU — that inaccuracy is the reason this ticket exists. Readings now split 1,426 `mapped` / 940 `null_mapped` / 215 `undecided`.

### Integrity checks on the finalized table

All clean: 0 readings with no `name_mappings` row, 0 `mapped` rows with a NULL `cardmarket_product_id`, 0 `mapped` ids that are missing or not `is_curated = 1`, and 0 `undecided` rows with `cardmarket_product_id` set (their best guess correctly lives in `llm_suggestion_id`).

### Mapping Review UI queue

`get_undecided_mappings` (`scraper/db.py:132`) returns **110 rows — down from 728**, covering 215 readings. 105 of the 110 arrive with a pre-filled `llm_suggestion_id`, so the operator confirms a dropdown rather than searching; only 5 have no suggestion at all. The queue is now what `undecided` was redefined to mean: unnamed-variant blisters/mini tins/checklanes where the catalog splits per featured Pokémon (`Poke Kiosk Blister ME05 REL 17/7`), plus the one empty-string raw_name.

### Follow-ups, none blocking

- **Two real sealed products will stay `null_mapped` until the next re-scrape** — `CBB1C: Gem Pack Vol. 1` and `WCD 2025: Riley McKay`, 2 readings each. Absent from the 2026-08-10 `cardmarket_catalogue.json` export; see step 1a.
- **The backfill `UPDATE` should carry a `WHERE product_id IS NOT NULL OR ...` guard** so its `rowcount` reports rows linked rather than rows touched. Cosmetic, but it made the finalize output read as a 2,581-row success.
- **Restore point:** `/opt/pokemon/pokemon.db.pre-ticket12-finalize` on Hetzner. Safe to delete once the new mappings have been reviewed in the UI.
