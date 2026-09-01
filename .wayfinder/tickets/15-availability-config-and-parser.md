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

## Outcome

Done. 23 configs migrated, 17 left with no block. The migration is faithful: replaying the 10 saved page fixtures through their real configs, old parser against new, gives **zero differing readings** (`in_stock`/`out_of_stock`/`None` mapping one-for-one onto the new states).

Choices the ticket left open:

- `availability_text` for the `presence` form is the matched element's text, and NULL for the absent branch. Nothing in the spec pinned this down; presence sites usually print something useful ("Varastossa", "Saatavilla 5 kpl") and the absent branch has no text to record by definition.
- A `presence` block missing the state for the branch that matched falls through to the next form instead of returning None, which is what makes "first hit wins" mean the same thing for every form.
- `availability_forms` returns NULL for a block that configures no form, so a block holding only a `default` reports as untracked rather than as tracked-but-blind. `tests/test_site_configs.py` also rejects such a block outright.
- `attribute` values are compared casefolded, unlike the old exact `== "InStock"`.
- `scrape_page` takes `from_preorder_url` and passes it down, but nothing supplies it yet: the `preorder_urls` config array, the paginator tagging and the `listings.from_preorder_url` write are ticket 17.
- `back_in_stock` now hangs off `availability_mode` being set rather than off `stock_mode` not being "unknown". Ticket 19 drops the guard entirely in favour of "no transition rule fires from or to unknown".

Four of the 17 untracked configs had an `in_stock` selector but no mode to read it with, so it went with the rest; the selectors are recorded in ticket 18 as its cheapest starting point. Also noted there: `prisma.fi`'s migrated `text_map` selector `.background-error p` matches nothing in the saved fixture, so all 33 of its listings read `in_stock` from the default. That is today's behaviour preserved, wrongly, exactly as this ticket intends.

From the code review, fixed here:

- `text_map` now iterates keys outer and elements inner, so "longest key first" holds across a
  container's elements instead of document order winning. No config has two keys yet, so the
  fixture replay is unchanged, but ticket 18's preorder keys would have hit this.
- A state outside `AVAILABILITY_STATES` is clamped to `unknown` with a warning naming the site.
  Passing a config typo through reached the `availability` CHECK constraint, and `run_site`'s
  broad `except` turned one bad listing into a site with zero listings and a cryptic error.
- `get_updates` orders by `created_at DESC, id DESC`. One run writes its whole batch inside a
  second, so without the tiebreaker which rows survive the 500-row cap was up to SQLite.
- `analyse_sites.py`'s config-generating prompt asked for `selectors.in_stock` and knew nothing
  about the block, so any new site's config would have failed the config tests.
- `.gitignore` covers `batch_*.csv`: 13 mapping-era files still sit untracked in the repo root.

Deferred with a home: the flag being unreachable for `presence` sites went to ticket 17 as a
decision it must make; a mid-run fetch failure silently dropping that run's events went to
ticket 19, which owns event writing. `preorder` → `in_stock` was already in 19.

Docs: `site_configs/_summary.md` documents the block, and `backlog.md`'s stock-detection item is marked superseded by tickets 15 to 18.

**Status: DONE**

Blocking: 16, 17, 19
Blocked by: 13
