# 12 — Run the accuracy pipeline

## Question

Execute the full accuracy overhaul pipeline end-to-end:

1. Run `scrape_catalog.md` in Copilot (operator passes captcha); save the output JSON file
2. Run `update_catalog.py` with the output file; verify matched count is reasonable
3. Run `llm_calibrate.md` in a Claude Code session; complete the 25-product calibration; confirm `calibration_examples.md` is written
4. Run `llm_batch_normalise.md` in batches of 100; review each CSV; annotate incorrect rows; run `apply_batch.py` after each verified batch
5. Once all batches are done, run `apply_batch.py --finalize`
6. Report final `name_mappings` counts (mapped / null_mapped / undecided) and `price_readings` backfill count

**Status: OPEN — steps 1–2 done 2026-08-13, steps 3–6 remain.** All four blockers (08, 09, 10, 11) are closed. Nothing left to build; this ticket is execution only.

Blocked by: 08, 09, 10, 11 — all closed

### Progress

- **Step 1 done (2026-08-13), with a deviation.** The browser session saved 8 plain-text dumps in the project root (`catalog_boosters.txt`, `catalog_booster_boxes.txt`, …) instead of one `catalog_scrape.json`. Each line is a link label plus a product URL; the listing pages never exposed the integer product id, so the dumps carry no `cardmarket_product_id` at all.
  - `scripts/extract_catalog.py` (new) converts the dumps to `catalog_scrape.json` in the ticket-07 schema, recovering ids by joining each product's URL slug to `cardmarket_catalogue.json`. See "Step 1a" below.
  - Result: **1,960 products, 1,942 with ids, 18 null.** Passes the step-1 sanity check.
- **Step 2 done (2026-08-13).** `matched: 1942`, `not_found: 0`. Verified on Hetzner: 1,942 rows at `is_curated=1`, ranks 1–300, popularity order intact (Boosters rank 1 = "Destined Rivals Booster"). Per-category: Boosters 297, Theme Decks 296, Booster Boxes 296, Blisters 295, Tins 295, Box Sets 294, Elite Trainer Boxes 157, Trainer Kits 12.
  - `not_found: 0` means the base catalogue did **not** need re-importing — every resolvable product was already in the 5,006-row import.
- **Steps 3–6 remain.** All are operator-interactive or destructive; see the runbook.

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

Two things the script handles that are worth knowing about:

- **Page-boundary repeats.** Several dumps repeat the last product of page N as the first of page N+1. Repeats are dropped so `popularity_rank` stays contiguous, but it means the scrape genuinely *missed* one product per overlap. Ranks are therefore approximate to within a few positions — fine for ordering, not exact.
- **Fold collisions.** The catalogue has a handful of same-named products under one category (e.g. two `Golisopod Stage 1 Blister` rows). These resolve to the lowest `idProduct` and are counted in the summary as `Ambiguous`. One occurred on the 2026-08-13 run.

The 18 unresolved slugs are printed by name. They are genuinely absent from the 2026-08-10 catalogue export — mostly sets released since (Ascended Heroes, 30th Celebration, WCD 2025, CSVH1C), plus `LocExpansionName-Blitzle-1-Pack-Blister`, which is a Cardmarket templating bug on their side. They stay in the JSON with a null id and get dropped by step 2. To curate them, re-export `cardmarket_catalogue.json` and re-run.

### Step 2 — apply to the DB *(automated, seconds)*

```bash
python scripts/update_catalog.py catalog_scrape.json
```

Verify `matched` is in the low thousands and `not_found` is small. `not_found` = products on Cardmarket now but absent from the 5,006-row `cardmarket_catalogue.json` import — i.e. sets released since that JSON was captured. A large `not_found` means the base catalogue needs re-importing before calibration, since those products can never be matched.

Note this command wipes existing curation first, so the curated set always reflects the newest scrape only.

### Step 3 — calibration *(interactive, 25 answers, ~45–90 min)*

Paste `copilot_prompts/llm_calibrate.md` into a Claude Code session. It picks 25 high-frequency raw_names stratified across large chains / small hobby shops / Swedish-language sites, then loops: shows 5 candidates, waits for `chosen_id`, `why_match`, and a `why_not` phrase per rejected candidate.

This is the quality-determining step — the reasoning text becomes the few-shot bank that steers all ~1,300 mappings. Spend real effort on the `why_not` phrases; they teach the distinctions that matter (booster pack vs. booster box, set-name collisions, language variants). Output: `copilot_prompts/calibration_examples.md`.

### Step 4 — batch normalisation *(interactive, ~13 batches, longest step)*

Paste `copilot_prompts/llm_batch_normalise.md` into a Claude Code session. Per batch of 100 it writes `batch_NNN.csv` then stops. For each batch:

1. Open the CSV; edit only the wrong rows (correct rows need no action)
2. `python scripts/apply_batch.py batch_NNN.csv`
3. Reply `next`

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
