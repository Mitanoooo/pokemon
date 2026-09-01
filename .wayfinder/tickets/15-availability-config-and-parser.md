# 15 — Availability config shape and parser

## Question

Replace `stock_mode` with one general `availability` config block and a parser that returns a four-state availability plus the raw text that produced it. See [spec](../spec-tracker-refocus.md) → "Availability config shape".

**Parser:** `detect_stock` becomes `detect_availability(container_el, config, from_preorder_url=False) -> tuple[str, str | None]`, returning one of `in_stock` / `out_of_stock` / `preorder` / `unknown` and an `availability_text` capped at 120 chars.

Resolution order, first hit wins:

1. `text_map` against the text of every element matching `selector`. Casefold and collapse whitespace on both sides; match keys as substrings, longest key first, so `"Ennakkotilaus 12.9.2026"` resolves to `preorder`. `availability_text` = the matched element's raw text.
2. `presence` — its own selector, with `present` and `absent` states.
3. `container_class_map` against the container's own class list. `availability_text` = classes joined by spaces.
4. `attribute` — `{"name": ..., "map": {...}}` on the element matching `selector`, or on the container when no selector.
5. `from_preorder_url` is true and nothing above matched → `preorder`, `availability_text` = `"(preorder url)"`.
6. `default` (normally `unknown`). No `availability` block at all → `unknown` immediately.

**Runner and db:** `scrape_page` returns `availability` and `availability_text` instead of `in_stock`. `upsert_listing` writes both, overwriting `availability` on every sighting (it means "state as of last sighting"). `update_site_health` also writes `sites.availability_mode` = the configured forms comma-joined in precedence order, or NULL when the config has no block.

**Config migration**, all 40 files, mechanical for the 23 that have a usable mode:

| Old | New |
|---|---|
| `normal` | `presence` with `present: in_stock`, `absent: out_of_stock` on the old `in_stock` selector |
| `inverted` | `presence` with the two swapped |
| `badge_text` | `text_map` `{<stock_badge_text>: out_of_stock}` plus `"default": "in_stock"` |
| `container_class` | `container_class_map` `{instock: in_stock, outofstock: out_of_stock, unavailable: out_of_stock}` |
| `attribute` | `attribute` block on `data-ls-availability` |
| `unknown` / absent | no `availability` block |

`stock_mode`, `stock_badge_text` and the `in_stock` selector are deleted from every config and from the parser. `tests/test_site_configs.py` gains a check that no config still names any of them, and that every `availability` block's state values are in the allowed set.

This migration is mechanical only: it preserves today's (wrong) readings for badge_text sites, where a preorder badge still resolves to `in_stock`. Ticket 18 fixes that per site with real HTML.

**Tests:** the 15 `detect_stock` tests are replaced per the spec's testing decisions, including precedence and `availability_text` content. Fixture-driven `scrape_page` tests for tcgkauppa, peliparatiisi and karkkainen move to the new return shape.

**Status: OPEN**

Blocking: 16, 17, 19
Blocked by: 13
