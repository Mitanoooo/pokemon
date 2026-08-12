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

**Status: OPEN**

Blocking: 12
Blocked by: 09 (calibration examples must exist before this prompt is useful)
