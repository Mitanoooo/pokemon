# 16 — Availability probe CLI

## Question

Write `scraper/probe.py` so pinning down a site's availability badges is a two-minute loop instead of guesswork. Operator tool, not part of a scrape run. See [spec](../spec-tracker-refocus.md) → "Probe tool".

```
python -m scraper.probe site_configs/tcgkauppa.fi.json [--url N] [--html-file page.html] [--limit 5]
python -m scraper.probe --all
```

Single-site mode fetches page 1 of each of the site's URLs (or reads `--html-file`), runs the config's `product_container` selector, and prints per site:

- distinct container class lists with counts
- distinct text of the configured `availability.selector` plus heuristic candidates: `[class*=stock]`, `[class*=avail]`, `[class*=badge]`, `[class*=saatav]`, `[class*=ennakko]`
- distinct `data-*` attribute values whose name contains `avail` or `stock`
- the availability split the current config produces, with the unknown share as a percentage
- up to `--limit` sample raw names per resolved state, so a wrong mapping is obvious by eye

`--all` loops every non-disabled config and prints one line per site: name, listings parsed, split by state, unknown share, configured forms. That output is the acceptance check for ticket 18. It respects the same 1-4s inter-fetch jitter as the scraper.

`--html-file` exists so the tool works against saved fixtures with no network, which is also how it gets tested.

**Tests:** one test that `--html-file` against an existing fixture in `tests/fixtures/` reports the expected split and badge census. No network in tests.

## Outcome

Done. `scraper/probe.py`, 13 tests in `tests/test_probe.py`, all fixture-driven so nothing in the
suite touches the network.

Beyond the ticket:

- **A configured selector that matches nothing gets its own line.** This is the failure the split
  cannot show: a `presence` selector that matches nothing reads every listing as its `absent`
  state, a `text_map` selector that matches nothing reads every listing as the `default`, and both
  produce a 0%-unknown split that looks solved. `prisma.fi`'s `.background-error p` is flagged on
  its fixture, which is the case ticket 15 wrote down. `--all` marks it `[no matches: <selector>]`.
  It is a prompt, not a verdict: a negative marker such as `porvoonpelikauppa.fi`'s `.out-of-stock`
  legitimately matches nothing on an all-in-stock page, and `karkkainen.com`'s fixture (60 of 60
  out of stock) trips it for exactly that reason. The line says so.
- **`presence.selector` is probed too.** The ticket only names `availability.selector`, but 14 of
  the 23 configs with a block keep the deciding selector under `presence`, so probing only the
  block-level key would have missed most of them.
- **Container class *tokens* print above class lists.** WooCommerce stamps the post id into the
  class list, so all 48 tcgkauppa containers have a distinct list and only the token counts show
  which class tracks stock (`outofstock` 42, `instock` 6). Both censuses print, capped at 12 rows.
- **A broken selector reports instead of raising.** soupsieve refuses to compile it and the parser
  raises mid-page; on a tool whose job is diagnosing configs, a traceback is the wrong answer. The
  container census still prints, and problems are deduped so a 14-URL site does not print the same
  one 14 times.
- **Samples print `(no badge text)`, not `(from default)`.** `detect_availability` returns NULL
  text for both the default and a matched-but-empty element (an icon-only sold-out marker), so the
  report cannot claim which one fired. Flagged in review.

`--all` fetches page 1 of *every* source URL of every site, not just the first, with the scraper's
1-4s jitter. That is slow (roughly 150 URLs) but ticket 18's acceptance number should not rest on
one category page per site.

`scrape_page`'s container lookup moved into `parser.find_containers`, which the probe reuses, so
`container_scope` cannot drift between the two.

Fixture sweep as it stands (10 saved pages, no network), which is ticket 18's starting point:

```
Karkkainen.com   60  in_stock=0  out_of_stock=60  unknown=0  presence  [no matches: .lipscore-rating-small[data-ls-availability="InStock"]]
KaruKortti        8  in_stock=1  out_of_stock=7   unknown=0  presence
Keräilykortti.fi 12  in_stock=3  out_of_stock=9   unknown=0  container_class_map
Peliparatiisi    16  in_stock=4  out_of_stock=12  unknown=0  text_map
Poromagia        20  in_stock=20 out_of_stock=0   unknown=0  presence
Porvoon Pelik.   24  in_stock=23 out_of_stock=1   unknown=0  presence
Prisma.fi        33  in_stock=33 out_of_stock=0   unknown=0  text_map  [no matches: .background-error p]
Proshop          20  in_stock=15 out_of_stock=5   unknown=0  presence
Spelparken        4  in_stock=3  out_of_stock=1   unknown=0  text_map
TCG-kauppa       48  in_stock=6  out_of_stock=42  unknown=0  container_class_map
```

Every one of these reports 0% unknown, which is the point of the flag: unknown share alone will
not tell ticket 18 which configs are actually right.

From the code review, findings that belong to code this ticket does not own, left for their owners:

- `presence` cannot tell "the shop says out of stock" from "the selector is wrong", and emits
  `back_in_stock` events when a shop's markup changes. Ticket 18 owns the readings; the probe is
  now the tool that finds these, and logging a zero-match page from the scraper itself belongs
  with 18 or 19.
- `_text_of` returning NULL for an icon-only badge conflates "from default" with "matched, no
  text". Parser semantics, ticket 18.
- `_state` warns once per listing, so a typo'd state logs ~240 identical lines per run. Ticket 18
  touches every block and can hoist the check to config load.
- `runner.py:230` calls `availability_forms` outside `run_site`'s `try`, so a malformed
  `availability` value (a string rather than an object) aborts the whole batch instead of one
  site. `tests/test_site_configs.py` rejects that shape today, so it needs a hand-edit to hit.
  Ticket 19 owns the runner.
- A `text_map` with no `selector` matches the whole container's text, so a product named "Tulossa
  2026" would read as preorder. No config uses that form; ticket 18 is where preorder keys arrive.

**Status: DONE**

Blocking: 18
Blocked by: 15
