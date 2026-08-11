# 03 — LLM mapping CLI script

## Question

What does the new `normaliser.py` (or replacement) look like?

- Reads all `raw_name`s from `price_readings` that have no row in `name_mappings`
- Calls Claude API with inline prompt; prompt lists all cardmarket product names from DB
- For each result: if confidence ≥ 0.85, inserts `status = mapped` (or `null_mapped`); otherwise inserts `status = undecided` with suggestion + confidence stored
- Reports counts at end (auto-mapped, suggested, skipped/error)
- Prompt template is a module-level constant in the script

**Status: CLOSED**

## Resolution

No Python script. The artefact is `copilot_prompts/llm_normalise.md` — a Claude Code prompt file you paste into a Claude Code session. It instructs Claude Code to:
1. Query `price_readings` for unmapped `raw_name`s
2. Load the `cardmarket_products` catalogue from SQLite
3. Process in batches of 50, applying the 0.85 threshold rule
4. Write results directly into `name_mappings` (INSERT OR IGNORE, commit per batch)
5. Report final counts by status

Re-usable: run the same prompt again whenever unmapped names accumulate — it skips already-mapped rows.

Blocking: 01, 02
Blocked by this: 05 (migration run)
