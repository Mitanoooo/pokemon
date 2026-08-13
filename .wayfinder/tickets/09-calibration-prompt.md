# 09 — Calibration session prompt

## Question

Write a Claude Code prompt (`copilot_prompts/llm_calibrate.md`) that runs a 25-product interactive calibration session and writes annotated examples to `copilot_prompts/calibration_examples.md`.

The prompt must:
1. Query the Hetzner server for the 25 raw_names with the highest `price_readings` count, stratified to ensure at least one raw_name per major retailer cluster (large chains, small hobby shops, Swedish-language sites)
2. For each raw_name: present the top 5 candidates from `cardmarket_products WHERE is_curated = 1 ORDER BY popularity_rank ASC`
3. Wait for operator input: chosen mapping (or "none"), reasoning for the match, brief note on why each rejected top candidate does not match
4. After all 25: write results to `copilot_prompts/calibration_examples.md`

Example format in the output file:
- raw_name
- Top-5 candidates shown (name + product ID)
- Chosen mapping (name + product ID, or null)
- Why it matched
- Why each rejected candidate didn't match

**Status: CLOSED**

## Resolution

`copilot_prompts/llm_calibrate.md` written (commit `f3013d6`). A Claude Code prompt, not a script — paste it into a session and it drives the interactive calibration.

**Structure:** connection block → fetch top-200 raw_names by reading count (with `GROUP_CONCAT` site names) → operator-agent picks 25 stratified across the three retailer clusters (large chains / small hobby shops / Swedish-language, each cluster defined by an explicit site-name pattern list) → fetch curated catalog (`is_curated = 1 ORDER BY popularity_rank ASC`) → 25-iteration loop → write `calibration_examples.md`.

**Candidate scoring:** `difflib.SequenceMatcher` ratio on lowercased names, `popularity_rank` as tiebreaker, top 5 shown.

**Loop contract:** each iteration prints a fixed block (raw_name, sites, 5 candidates) and then stops for the operator to supply `chosen_id` (or `none`), `why_match`, and a `why_not` phrase per rejected candidate. The prompt explicitly forbids advancing until all fields are answered.

**Output:** `copilot_prompts/calibration_examples.md` — 25 examples, each with raw_name, the 5 candidates shown, the chosen mapping, why it matched, and why each rejected candidate didn't. Becomes the few-shot bank for ticket 10.

### Amended 2026-08-13 after the first real run (ticket 12, step 3)

Two parts of the prompt as built did not survive contact with the data; both are now corrected in `llm_calibrate.md`.

- **The selection rule was unusable.** Reading counts are flat — 1,172 of 1,304 distinct raw_names have exactly 2 readings — so `ORDER BY reading_count DESC LIMIT 200` returns ~33 genuinely frequent names and 167 in SQLite's tie order. The "Swedish-language" cluster does not exist either (one `.se` site, listings in English; Finnish is the real second language). And high-frequency names are disproportionately *easy*: 54 of the 1,304 are exact catalog-name matches, which teach nothing. Selection is now by **difficulty**, with an explicit list of the hard patterns to cover.
- **The top-5 candidate list is a presentation limit, not a search limit.** The fixed `difflib` ratio is whole-string, so a long retailer prefix outranks the set name — for `Scarlet &amp; Violet: Paradox Rift booster` all five candidates are Scarlet & Violet base-set rows and the correct `Paradox Rift Booster` is absent. Ten of the 25 shipped examples were like this. `scripts/calibration_candidates.py` (new) implements the scoring rule and adds a token-overlap list below the top 5; the operator may name any product id.

Also added: a `status` field per answer (`mapped` / `null_mapped` / `undecided`), since the session produced a three-way decision the original format had no field for, and observed price per raw_name, which turned out to be the decisive pack-vs-box signal. `tests/test_calibration_examples.py` asserts the output structure.

Blocking: 10, 12
Blocked by: 08 (curated catalog must be populated in DB before candidates can be shown)
