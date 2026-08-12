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

**Status: OPEN**

Blocking: 10, 12
Blocked by: 08 (curated catalog must be populated in DB before candidates can be shown)
