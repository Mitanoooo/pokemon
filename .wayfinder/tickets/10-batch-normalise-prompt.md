# 10 — Batch normalization prompt

## Question

Write a Claude Code prompt (`copilot_prompts/llm_batch_normalise.md`) that supersedes `llm_normalise.md` as the primary normalization tool.

The prompt must:
- Fetch all raw_names from `price_readings` not yet present in the local `draft_mappings.json` accumulation file
- Process in batches of 100, pausing between batches for operator review
- Include in prompt context:
  - Full `calibration_examples.md` as few-shot examples
  - Curated catalog (`is_curated = 1`) sorted by `popularity_rank` ASC (most popular first)
  - Classification rule: include if product belongs to one of the 8 curated categories; null_map everything else
  - Finnish→English translation glossary carried over from `llm_normalise.md`
- Soft prior: when two candidates are equally plausible, prefer the lower `popularity_rank` (more popular) one
- Status rules:
  - `mapped`: confident match to a curated product
  - `null_mapped`: confirmed not a sealed TCG product
  - `undecided`: rare fallback — only for raw_names that are genuinely unrecognizable (garbled, encoding errors, too short). Not a substitute for "I'm uncertain which product this is."
- Output per batch: CSV file with columns `raw_name`, `proposed_name`, `cardmarket_product_id`, `confidence`, `status`
- After outputting the CSV, pause for operator review before proceeding to the next batch

Operator reviews the CSV and annotates only incorrect rows (correct rows require no action).

**Status: CLOSED**

## Resolution

`copilot_prompts/llm_batch_normalise.md` written (commit `d641a5b`). Supersedes `llm_normalise.md`. Seven steps:

1. Fetch all distinct `raw_name`s from `price_readings` on Hetzner
2. Read local `draft_mappings.json` (empty list if absent), compute `todo` as the set difference, print a batch-count summary, exit early if empty
3. Fetch curated catalog (`is_curated = 1 ORDER BY popularity_rank ASC`)
4. Read `calibration_examples.md` into context
5. Normalisation rules — the 8 in-scope categories, an explicit out-of-scope list (singles, other TCGs, toys/plush/sleeves/binders/playmats/Funko/LEGO), the status table, the popularity soft prior, and the Finnish→English glossary (plus three Swedish terms)
6. Batch loop of 100: assess → write `batch_NNN.csv` → print status counts → **stop for operator review**
7. Session summary with remaining-todo count and the finalize command

**Status discipline as built:** `undecided` is restricted to genuinely uninterpretable text (garbled, encoding errors, too short, unrecognised language). The prompt states in bold that uncertainty between two products is *not* grounds for `undecided` — pick the more popular one. A raw_name that is clearly an in-scope sealed product but absent from the curated catalog gets `null_mapped` rather than a forced low-confidence match.

**Operator replies recognised at the batch pause:** `next`/`done` (advance), `stop` (end session, print summary), `skip` (discard the CSV and re-run the same 100 names).

### Amended 2026-08-13 after the step-3 calibration (ticket 12)

The calibration session established policies this prompt had no way to express, so it was amended before step 4 ran.

- **Price is now fetched and used.** Step 1 returns each raw_name's `MIN`/`MAX` price, currency and sites alongside the name, and a new § 5f uses it to separate product forms: single packs read 4.90–7.29 EUR against 199.90–389.50 EUR for display boxes, and 26% of tracked raw_names are a bare "Booster"/"Boosteri" with no qualifier at all. § 5f is written **form → price, to be read as an exclusion filter** rather than a price → form lookup, because the observed ranges overlap: 80.00 EUR is an ETB (example 1) and also sits inside the Japanese-booster-box range, and 41.95 EUR is a Chinese booster box (example 8) and also sits inside the ETB range. Only the downward direction is safe — scalping raises prices, never lowers them (a single Prismatic Evolutions pack at 20.95 EUR, a plain ETB at 149.00 EUR). Batch CSVs gain a trailing review-only `observed_price` column.
- **`undecided` gained a second trigger.** As built it was reserved for uninterpretable text. The operator added: product family certain but the featured Pokémon unnamed (blisters, checklane blisters, mini tins, sticker collections are listed per Pokémon) → `undecided` with the lowest-rank variant as best guess. This directly contradicted the "uncertainty is not grounds for `undecided`" rule as written, which now applies only to a choice between two *different products*.
- **§ 5b2 added — six binding operator rules** with the example numbers that demonstrate each: random assortments → `null_mapped`; unnamed variant → `undecided`; multi-unit cases → the single-unit row; plain edition over Pokémon Center; bare "Booster" → the single-pack row; box-break / Rip & Ship services → `null_mapped`. Rule precedence is stated (unnamed variant outranks the case rule).
- **§ 5c rewritten to strip retailer noise first and search the whole catalog.** Ten of the 25 calibration examples have their correct product outside the `difflib` top five, so ranking by string similarity and stopping at the top few is explicitly ruled out.
- **§ 5a now lists the literal `category` strings.** The prose labels did not match the data: "Booster Boxes" is `Pokémon Display` and "Theme Decks" is `Pokémon Theme Deck`, singular.

`apply_batch.py` needed no change — `csv.DictReader` pulls named fields, so the extra column is ignored. That is now covered by `tests/test_apply_batch.py` rather than assumed.

Blocking: 12
Blocked by: 09 (calibration examples must exist before this prompt is useful)
