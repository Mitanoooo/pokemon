# 18 — Availability pin-down pass across all 40 sites

## Question

Fill in a real `availability` block for every site, checked against live HTML with the probe. This is the ticket that makes back-in-stock and preorder detection trustworthy; everything else is scaffolding around it. See [spec](../spec-tracker-refocus.md) → "Availability config shape" and "Further Notes".

Starting point after ticket 15: 23 sites carry a mechanically migrated block that reproduces today's readings (including the badge_text sites, where a preorder badge still resolves to `in_stock`), and 17 sites have no block at all (11 never had `stock_mode`, 6 set `"unknown"`).

Four of those 17 had an `in_stock` selector written but no mode to interpret it, so ticket 15 deleted the selector along with the rest. They are the cheapest four to start on, and these are the selectors that were there:

| Site | Old `in_stock` selector |
|---|---|
| euroelite.fi | `.product-stock-balance-in-stock` |
| fantasialinna.com | `.in-stock` |
| konsolinet.fi | `.AvailabilityInStock` |
| vpd.fi | `.stock-status.available` |

Two known-wrong migrated blocks to check early: `prisma.fi`'s `text_map` selector is `.background-error p`, and the saved fixture's class is `bg-color-background-error`, so nothing matches and every listing reads `in_stock` from the default. `tcgkauppa.fi` and the other WooCommerce sites were on `container_class`, which is fine, but their old descendant selector (`li.product.instock`) never matched anything either.

**Per site:**

1. Run `python -m scraper.probe site_configs/<site>.json`.
2. Read the badge census. Map every state-bearing text or class to `in_stock`, `out_of_stock` or `preorder`. Preorder wording to look for: ennakkotilaus, ennakko, tulossa, saapuu, julkaisu, preorder, pre-order, kommer, släpp.
3. Write the block, re-run the probe, and confirm the split moves.
4. Where the listing page genuinely carries no state signal, leave the block out and record why. The app then shows that site as "not tracked", which is the honest answer and is the point of distinguishing a missing block from `unknown`.

**Acceptance bar:** `python -m scraper.probe --all` shows every site either under 5% `unknown` or with no `availability` block and a recorded reason. No site sits in the middle.

**Deliverable:** `.scratch/tracker-refocus/availability-pass.md`, one section per site: badge texts and classes found, the block written, resulting split, and for untracked sites the reason.

**Watch for:** shops whose out-of-stock items are simply absent from the listing page. Those look like 100% `in_stock` coverage while actually tracking nothing, and their disappearing listings cannot be read as out of stock (ruled out in the spec's Out of Scope). Record them as tracked-in-stock-only in the deliverable so the coverage number is not read as more than it is.

**Tests:** per-site fixture tests are added only for sites whose config needed a non-obvious mapping; the rest are covered by ticket 15's parser tests plus the probe run.

**Status: OPEN**

Blocking: nothing
Blocked by: 16
