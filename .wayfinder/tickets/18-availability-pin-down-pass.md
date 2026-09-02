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

Unknown share alone is not enough to clear a site: all 10 configs with a saved fixture already report 0% unknown, `prisma.fi` included, because a selector that matches nothing sends every listing to the `default` or the `presence` `absent` state. Ticket 16 added a `[no matches: <selector>]` marker to the `--all` line for that case, so read the acceptance bar as "under 5% unknown **and** no unmatched-selector marker". The marker also fires legitimately when a negative marker finds nothing on an all-in-stock page (`karkkainen.com`'s fixture, `porvoonpelikauppa.fi`), so each one needs an eyeball on the page, not a blanket fix.

**Deliverable:** `.scratch/tracker-refocus/availability-pass.md`, one section per site: badge texts and classes found, the block written, resulting split, and for untracked sites the reason.

**Watch for:** shops whose out-of-stock items are simply absent from the listing page. Those look like 100% `in_stock` coverage while actually tracking nothing, and their disappearing listings cannot be read as out of stock (ruled out in the spec's Out of Scope). Record them as tracked-in-stock-only in the deliverable so the coverage number is not read as more than it is.

**Tests:** per-site fixture tests are added only for sites whose config needed a non-obvious mapping; the rest are covered by ticket 15's parser tests plus the probe run.

**Status: DONE**

Result (`.scratch/tracker-refocus/availability-pass.md`): 27 of the 29 enabled configs carry
an availability block checked against live HTML. `probe --all` puts every one of them at 0%
unknown. karkkainen.com lost its block on purpose — all 57 cards report `OutOfStock` in
Lipscore markup, including items its own product pages call in stock — so it is the one site
that reads as not tracked, with the reason in its `notes` and in the deliverable.

One site does not fit either end of the bar: kevinshobbyshop.com answers HTTP 403 to every
request from this network, front page included, so its block could not be checked and its
`--all` line reads 0 listings. Its class map is the WooCommerce default, which is the best
guess available without the HTML; dropping the block would only make an unchecked site look
deliberately untracked. It needs a re-run from the server, which is where several other
configs already wait for a reachability check.

Two `[no matches: ...]` markers remain, both eyeballed: God of Cards and JR Kodintavaratalo are
negative markers on all-in-stock Pokemon listings, verified against the unfiltered collection
(27/5) and /lego (14/10) respectively. Kevin's Hobby Shop's line carries the `[HTTP 403 ...]`
marker instead, which is the fetch failure, not an unmatched selector.

Blocks fixed rather than written: prisma.fi's `text_map` selector matched nothing so every
listing read in stock, blockhousegames.net's presence check read sold-out cards as in stock
(the element is on both states), and fantasialinna.com's `.in-stock` selector from the table
above does not exist on the live page (the state is `div.stock` text). Preorder now reads as
preorder on five sites that showed none: korttistoppi (22), maxgaming (10), pelimies (6),
poromagia (2), swagykarp (8).

Six sites are tracked in-stock-only, recorded as such because their split looks like perfect
coverage and is not: blockhousegames.net, ellimadelli.fi, godofcards.com, muksumassi.fi,
muovijalelu.fi, pelimies.fi. Their listing pages never show a sold-out product.

Two mappings were rejected on the evidence: porvoonpelikauppa's `Julkaisu <date>` free text
(dates that have passed are still shown, so it would strand released products in preorder) and
the "ennakko" wording in product names at ellimadelli and peliparatiisi (nothing in the
pipeline reads names).

Two dead keys removed: flea.fi and godofcards.com set `"default": "unknown"` under a presence
block that sets both `present` and `absent`, so nothing could reach the default.

One parser change came out of the pass: `container_class_map` recorded the container's whole
class list as `availability_text`, and on swagykarp's ~20-class cards the 120-char cap cut off
the class that decided the state. It now falls back to the matched class alone.

Tests: `tests/test_availability_configs.py`, 23 cases over 8 sites, each fixture a saved page
trimmed to a few cards per state (12-32 kB), plus the untracked-karkkainen guard.

Blocking: nothing
Blocked by: 16
