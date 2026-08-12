# 12 — Run the accuracy pipeline

## Question

Execute the full accuracy overhaul pipeline end-to-end:

1. Run `scrape_catalog.md` in Copilot (operator passes captcha); save the output JSON file
2. Run `update_catalog.py` with the output file; verify matched count is reasonable
3. Run `llm_calibrate.md` in a Claude Code session; complete the 25-product calibration; confirm `calibration_examples.md` is written
4. Run `llm_batch_normalise.md` in batches of 100; review each CSV; annotate incorrect rows; run `apply_batch.py` after each verified batch
5. Once all batches are done, run `apply_batch.py --finalize`
6. Report final `name_mappings` counts (mapped / null_mapped / undecided) and `price_readings` backfill count

**Status: OPEN**

Blocked by: 08, 09, 10, 11
