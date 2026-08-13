# Calibration Examples

Generated during the calibration session (ticket 09). Used as few-shot examples
in the batch normalisation prompt (ticket 10).

Total: 25 examples

## How this bank was selected

These 25 raw_names were **not** picked by reading frequency. Reading counts are
almost flat — of 1,304 distinct raw_names, one has 8 readings, two have 6, 28 have
4 and 1,172 have exactly 2 — so a "top 200 by frequency" slice is mostly tie-order
artefact and 54 of those names are exact string matches that need no guidance.

Each example was instead chosen because a naive match gets it wrong, and each one
encodes a decision policy that cannot be inferred from the catalog alone. The
policies are stated in "Operator decision rules" below; apply those rules first and
use the worked examples for the matching style and the wording of the distinctions.

Candidate lists are the real output of the step-3 scorer
(`scripts/calibration_candidates.py`: `difflib.SequenceMatcher` ratio on lowercased
names, `popularity_rank` ascending as tiebreaker). In **ten** of the 25 examples
(1, 2, 3, 7, 8, 15, 19, 20, 23, 25) the chosen product **does not appear in the top
five at all** — that is the point of those examples, and it is why the batch prompt
searches the whole catalog rather than a top-5 shortlist.

## Operator decision rules

| # | Situation | Rule | Examples |
|---|---|---|---|
| 1 | Retailer ships "1 of N random selection" | `null_mapped` — no single row is the product sold | 5, 6, 12 |
| 2 | Product family is certain but the featured Pokémon is unnamed | `undecided`, with the lowest-rank variant as best guess | 3, 4, 11, 23 |
| 3 | Retailer sells a multi-unit case (`Case (12)`, `Booster Box (6)`) | Map to the **single-unit** row | 11 |
| 4 | Catalog has both a plain and a Pokémon Center edition | Prefer the **plain** retail edition | 15 |
| 5 | Bare "Booster" / "Boosteri" / "Boosterpakkaus", no box qualifier | The single-pack `<Set> Booster` row | 2, 16, 19, 20, 21 |
| 6 | Listing sells a service, not a product ("BOX BREAK", "Rip & Ship") | `null_mapped` — the buyer receives loose cards | 9, 10 |

Rule 2 outranks rule 3: a case of an unnamed variant is `undecided` (example 11).

Rule 3 has a known consequence the operator accepted deliberately — a case price is
6-12x the single-unit price, so those readings will surface as price outliers.

### Price as a prior

Observed listing price separates pack from box decisively in most cases: single
packs read 4.90-7.29 EUR against 199.90-389.50 EUR for display boxes. It is a
**prior, not a rule** — heavily scalped sets break it. In example 16 a single
Prismatic Evolutions pack lists at 20.95 EUR, and in example 15 a plain Elite
Trainer Box lists at 149.00 EUR, above the Pokémon Center edition's usual premium.
Prices below ~4 EUR usually indicate a service slot (examples 9 and 10) rather than
any sealed product.

---

## Example 1

**raw_name:** `Poke ME05 Elite Trainer Box REL 17/7`

**Sites:** Prisma.fi  ·  **Observed price:** 80.00 EUR

**Candidates shown:**
1. Pokémon GO 10 Elite Trainer Box Case (ID: 690879) — Pokémon Elite Trainer Boxes, rank 125, score 0.6944
2. Pokémon GO Elite Trainer Box (ID: 653700) — Pokémon Elite Trainer Boxes, rank 24, score 0.6875
3. 151 10 Elite Trainer Box Case (ID: 719692) — Pokémon Elite Trainer Boxes, rank 143, score 0.6769
4. 151 Elite Trainer Box (ID: 719691) — Pokémon Elite Trainer Boxes, rank 29, score 0.6667
5. Perfect Order 10 Elite Trainer Box Case (ID: 865394) — Pokémon Elite Trainer Boxes, rank 146, score 0.6667

**Chosen mapping:** Pitch Black Elite Trainer Box (ID: 885542) — **mapped**

**Status:** `mapped`

**Why it matched:** `ME05` is the retailer's code for the fifth Mega Evolution set, Pitch Black, and `REL 17/7` is a release date rather than part of the product name; strip both and this is the plain retail Elite Trainer Box. The 80.00 EUR price fits a single ETB (a 10-unit case would be several hundred), and Prisma is a mass-market grocery chain that does not carry Pokémon Center exclusives.

**Why candidates didn't match:**
- Pokémon GO 10 Elite Trainer Box Case: right product type but the wrong set, and a 10-unit case rather than one ETB
- Pokémon GO Elite Trainer Box: matched only on the words "Elite Trainer Box" — Pokémon GO is a 2022 set unrelated to ME05
- 151 10 Elite Trainer Box Case: wrong set and a 10-unit case; "151" is a coincidental digit match
- 151 Elite Trainer Box: wrong set — nothing in the listing points to the 151 expansion
- Perfect Order 10 Elite Trainer Box Case: Perfect Order is ME03, not ME05, and this is again a 10-unit case

---

## Example 2

**raw_name:** `Pokemon ME04 Booster`

**Sites:** JR Kodintavaratalo  ·  **Observed price:** 5.95 EUR

**Candidates shown:**
1. Pokémon GO Booster (ID: 653699) — Pokémon Booster, rank 64, score 0.7895
2. Pokémon Card 151 Booster (ID: 704498) — Pokémon Booster, rank 49, score 0.6818
3. Crimson Haze Booster (ID: 757140) — Pokémon Booster, rank 87, score 0.65
4. Violet ex Booster (ID: 689086) — Pokémon Booster, rank 77, score 0.6486
5. Paldean Fates Booster (ID: 745544) — Pokémon Booster, rank 30, score 0.6341

**Chosen mapping:** Chaos Rising Booster (ID: 877296) — **mapped**

**Status:** `mapped`

**Why it matched:** `ME04` decodes to Chaos Rising. Unqualified "Booster" means the single pack, not the display box — the 5.95 EUR price settles it, since a 36-pack box runs 200-380 EUR.

**Why candidates didn't match:**
- Pokémon GO Booster: correct product type but an unrelated 2022 set; matched on the bare word "Booster"
- Pokémon Card 151 Booster: wrong set, and the Japanese "Pokémon Card" line rather than the English release
- Crimson Haze Booster: wrong set, no relation to ME04
- Violet ex Booster: wrong set and a Japanese release
- Paldean Fates Booster: wrong set; ranked high only for being a short "<Set> Booster" string

---

## Example 3

**raw_name:** `Pokemon Blister 3P ME05`

**Sites:** JR Kodintavaratalo  ·  **Observed price:** 21.95 EUR

**Candidates shown:**
1. Pokémon GO Booster (ID: 653699) — Pokémon Booster, rank 64, score 0.5854
2. Pokémon GO: Blissey Mini Tin (ID: 653713) — Pokémon Tins, rank 15, score 0.549
3. Pokémon GO: Blissey Tin (ID: 653710) — Pokémon Tins, rank 75, score 0.5217
4. Pokémon Card 151 Booster (ID: 704498) — Pokémon Booster, rank 49, score 0.5106
5. Pokémon Card 151 Booster Box (ID: 718514) — Pokémon Display, rank 23, score 0.5098

**Chosen mapping:** Pitch Black: Binacle 3-Pack Blister (ID: 885533) — **undecided**, best guess only

**Status:** `undecided`

**Why it matched:** The family is certain — `ME05` is Pitch Black and `3P` is a 3-pack blister, consistent with the 21.95 EUR price — but Cardmarket lists 3-pack blisters per featured Pokémon and this listing names none. Recorded as `undecided` with Binacle (the only Pitch Black 3-pack row) as the best guess rather than asserting a variant the retailer never stated.

**Why candidates didn't match:**
- Pokémon GO Booster: wrong set and wrong product type — a single booster, not a blister
- Pokémon GO: Blissey Mini Tin: a mini tin, not a blister, and an unrelated set
- Pokémon GO: Blissey Tin: a full-size tin from an unrelated set
- Pokémon Card 151 Booster: wrong set and wrong type
- Pokémon Card 151 Booster Box: wrong set and a 36-pack display box

---

## Example 4

**raw_name:** `Pokemon TCG: ME04 Chaos Rising – Checklane Blister`

**Sites:** Muksumassi  ·  **Observed price:** 8.95 EUR, 10.95 EUR

**Candidates shown:**
1. Chaos Rising: Flygon Premium Checklane Blister (ID: 877289) — Pokémon Blisters, rank 42, score 0.6458
2. Chaos Rising: Pawmot Premium Checklane Blister (ID: 877288) — Pokémon Blisters, rank 80, score 0.6458
3. Scarlet & Violet: Machamp Premium Checklane Blister (ID: 695518) — Pokémon Blisters, rank 157, score 0.5941
4. Chaos Rising: Charmeleon 3-Pack Blister (ID: 877290) — Pokémon Blisters, rank 4, score 0.5843
5. Chaos Rising: Toxel 1-Pack Blister (ID: 877285) — Pokémon Blisters, rank 150, score 0.5714

**Chosen mapping:** Chaos Rising: Flygon Premium Checklane Blister (ID: 877289) — **undecided**, best guess only

**Status:** `undecided`

**Why it matched:** Set and product type are both explicit (`ME04` = Chaos Rising, checklane blister, 8.95-10.95 EUR), but Cardmarket only carries per-Pokémon checklane rows — Flygon and Pawmot — and the listing names neither. Same rule as example 3: the unnamed variant stays `undecided`.

**Why candidates didn't match:**
- Chaos Rising: Flygon Premium Checklane Blister: correct set and type, but choosing it assumes Flygon, which the listing never says
- Chaos Rising: Pawmot Premium Checklane Blister: exactly as plausible as Flygon — that tie is what makes this undecided
- Scarlet & Violet: Machamp Premium Checklane Blister: right product type, wrong set
- Chaos Rising: Charmeleon 3-Pack Blister: correct set but a 3-pack blister, a different product from a checklane
- Chaos Rising: Toxel 1-Pack Blister: correct set but a 1-pack blister

---

## Example 5

**raw_name:** `Pokemon Tin Box Paldea Legends Koraidon ex / Miraidon ex 1 of 2 random selection`

**Sites:** God of Cards  ·  **Observed price:** 42.13 EUR

**Candidates shown:**
1. Paldea Legends Tins: Miraidon ex Tin (ID: 703203) — Pokémon Tins, rank 40, score 0.569
2. Paldea Legends Tins: Koraidon ex Tin (ID: 703205) — Pokémon Tins, rank 26, score 0.5172
3. Slashing Legends Tins: Koraidon ex Tin (ID: 813960) — Pokémon Tins, rank 39, score 0.4407
4. Paldean Fates: Meowscarada ex Premium Collection (ID: 745562) — Pokémon Box Set, rank 175, score 0.4375
5. Greninja ex & Kingdra ex Special Collection (ID: 833714) — Pokémon Box Set, rank 243, score 0.4228

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** The retailer ships one of two different tins chosen at random, so no single catalog row is the product being priced. Mapping to either would attribute a price to a product the buyer may not receive.

**Why candidates didn't match:**
- Paldea Legends Tins: Miraidon ex Tin: one of the two possible outcomes, not the thing actually sold
- Paldea Legends Tins: Koraidon ex Tin: the other possible outcome — picking either is a coin flip
- Slashing Legends Tins: Koraidon ex Tin: wrong set: Slashing Legends, not Paldea Legends
- Paldean Fates: Meowscarada ex Premium Collection: a different set and a premium collection rather than a tin
- Greninja ex & Kingdra ex Special Collection: an unrelated product matched on the "ex &" shape

---

## Example 6

**raw_name:** `PokemonObsidian Flames3-Pack BlisterEevee / Houndstone1 out of 2 random selection`

**Sites:** God of Cards  ·  **Observed price:** 31.59 EUR

**Candidates shown:**
1. Obsidian Flames: Eevee 3-Pack Blister (ID: 715773) — Pokémon Blisters, rank 79, score 0.4915
2. Obsidian Flames: Pawmi 1-Pack Blister (ID: 715774) — Pokémon Blisters, rank 20, score 0.4746
3. Obsidian Flames: Houndstone 3-Pack Blister (ID: 715772) — Pokémon Blisters, rank 41, score 0.4715
4. Enhanced 2-Pack Blister: Munkidori, Okidogi & Fezandipiti (ID: 818378) — Pokémon Blisters, rank 71, score 0.4638
5. Obsidian Flames 6 Booster Box Case (ID: 715779) — Pokémon Display, rank 271, score 0.4522

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** The same random-assortment rule as example 5. Note that this retailer's markup strips separators, so brand, set, type and Pokémon names run together (`PokemonObsidian Flames3-Pack Blister...`) — that mangling makes the string harder to read but does not change the decision.

**Why candidates didn't match:**
- Obsidian Flames: Eevee 3-Pack Blister: one of the two random outcomes
- Obsidian Flames: Pawmi 1-Pack Blister: wrong Pokémon and a 1-pack rather than a 3-pack
- Obsidian Flames: Houndstone 3-Pack Blister: the other random outcome
- Enhanced 2-Pack Blister: Munkidori, Okidogi & Fezandipiti: a different blister line and a 2-pack
- Obsidian Flames 6 Booster Box Case: correct set only — a case of booster boxes, not a blister

---

## Example 7

**raw_name:** `Pokemon TCG - Mega Evolution - Abyss Eye (M5) - Booster Box (Japaniksi)`

**Sites:** PBCards  ·  **Observed price:** 90.95 EUR

**Candidates shown:**
1. Mega Evolution 6 Enhanced Booster Box Case (ID: 835600) — Pokémon Display, rank 262, score 0.5841
2. Mega Evolution 6 Booster Box Case (ID: 834812) — Pokémon Display, rank 277, score 0.5769
3. Mega Evolution 24 Sleeved Booster Case (ID: 834811) — Pokémon Display, rank 203, score 0.5505
4. Mega Evolution Enhanced Booster Box (ID: 834827) — Pokémon Display, rank 136, score 0.5472
5. Mega Evolution Booster Box (18 Boosters) (ID: 834825) — Pokémon Display, rank 148, score 0.5405

**Chosen mapping:** Abyss Eye Booster Box (ID: 883955) — **mapped**

**Status:** `mapped`

**Why it matched:** Cardmarket names the Japanese sub-set directly as "Abyss Eye", so the sub-set in parentheses (`M5`) is what to match on — not the "Mega Evolution" umbrella the retailer puts in front. `(Japaniksi)` is Finnish for "in Japanese", consistent with Abyss Eye being a Japanese-only release, and 90.95 EUR is the going rate for a Japanese box. **The correct row does not appear in the top five at all** — the umbrella prefix dominates the string score.

**Why candidates didn't match:**
- Mega Evolution 6 Enhanced Booster Box Case: matched the umbrella name; a 6-box case of the English Enhanced product
- Mega Evolution 6 Booster Box Case: umbrella name again, and a 6-box case rather than one box
- Mega Evolution 24 Sleeved Booster Case: a case of 24 sleeved single packs
- Mega Evolution Enhanced Booster Box: the English Enhanced box — a different SKU from the Japanese Abyss Eye box
- Mega Evolution Booster Box (18 Boosters): English half-size box: wrong language and wrong pack count

---

## Example 8

**raw_name:** `Pokemon TCG - Scarlet & Violet - Gem Pack Vol. 4 (CBB4C) - Booster Box (Yksinkertaistettu Kiina)`

**Sites:** PBCards  ·  **Observed price:** 41.95 EUR

**Candidates shown:**
1. Pokémon Card Gym Promo Scarlet & Violet Vol. 4 Booster (ID: 740421) — Pokémon Booster, rank 240, score 0.56
2. Pokémon Card Gym Promo Scarlet & Violet Vol. 9 Booster (ID: 807418) — Pokémon Booster, rank 113, score 0.5467
3. Pokémon Card Gym Promo Scarlet & Violet Vol. 8 Booster (ID: 793378) — Pokémon Booster, rank 121, score 0.5467
4. Pokémon Card Gym Promo Scarlet & Violet Vol. 7 Booster (ID: 778390) — Pokémon Booster, rank 207, score 0.5467
5. Pokémon Card Gym Promo Scarlet & Violet Vol. 5 Booster (ID: 751818) — Pokémon Booster, rank 218, score 0.5467

**Chosen mapping:** CBB4C: Gem Pack Vol. 4 Booster Box (ID: 866295) — **mapped**

**Status:** `mapped`

**Why it matched:** Cardmarket prefixes Simplified Chinese sets with their set code, so the `CBB4C` in the listing matches the catalog row exactly. `Yksinkertaistettu Kiina` is Finnish for Simplified Chinese and confirms the region; 41.95 EUR fits a Chinese box, which is cheaper than the English or Japanese equivalents. Again the correct row sits outside the top five.

**Why candidates didn't match:**
- Pokémon Card Gym Promo Scarlet & Violet Vol. 4 Booster: matched "Scarlet & Violet" and "Vol. 4", but this is a Japanese Gym promo booster, not a Chinese Gem Pack box
- Pokémon Card Gym Promo Scarlet & Violet Vol. 9 Booster: wrong product line and the volume number does not match either
- Pokémon Card Gym Promo Scarlet & Violet Vol. 8 Booster: wrong product line, wrong volume
- Pokémon Card Gym Promo Scarlet & Violet Vol. 7 Booster: wrong product line, wrong volume
- Pokémon Card Gym Promo Scarlet & Violet Vol. 5 Booster: wrong product line, wrong volume

---

## Example 9

**raw_name:** `BOX BREAK: Pokémon SV6: Twilight Masquerade Booster`

**Sites:** TCG-kauppa  ·  **Observed price:** 3.98 EUR

**Candidates shown:**
1. Twilight Masquerade Booster (ID: 761217) — Pokémon Booster, rank 31, score 0.6923
2. Twilight Masquerade Booster Box (ID: 761219) — Pokémon Display, rank 61, score 0.6585
3. Twilight Masquerade Booster Bundle (ID: 761221) — Pokémon Display, rank 160, score 0.6353
4. Twilight Masquerade Sleeved Booster (ID: 761218) — Pokémon Booster, rank 126, score 0.6279
5. Twilight Masquerade 6 Booster Box Case (ID: 761232) — Pokémon Display, rank 214, score 0.6067

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** A box break is a paid slot in a live group opening — the buyer receives whatever cards are pulled on stream, not a sealed product. The 3.98 EUR price is decisive: it is far below a single pack, let alone the box being opened. This one is dangerous precisely because the set name matches a real row at 0.69 similarity.

**Why candidates didn't match:**
- Twilight Masquerade Booster: the set is right, but the listing sells participation in an opening, not a sealed pack
- Twilight Masquerade Booster Box: this is the box that gets opened on stream; it is not what the customer receives
- Twilight Masquerade Booster Bundle: same reasoning, and no bundle is mentioned
- Twilight Masquerade Sleeved Booster: same reasoning; "sleeved" appears nowhere in the listing
- Twilight Masquerade 6 Booster Box Case: same reasoning, and a 6-box case at that

---

## Example 10

**raw_name:** `Kaskem PITCH BLACK Rip&Ship (17.7.2026)`

**Sites:** TCG-kauppa  ·  **Observed price:** 3.90 EUR

**Candidates shown:**
1. Pitch Black Booster Box (ID: 885545) — Pokémon Display, rank 1, score 0.4516
2. Pitch Black Booster (ID: 885547) — Pokémon Booster, rank 3, score 0.4483
3. Pitch Black Booster Box (18 Boosters) (ID: 885544) — Pokémon Display, rank 59, score 0.4474
4. Pitch Black Elite Trainer Box (ID: 885542) — Pokémon Elite Trainer Boxes, rank 1, score 0.4412
5. Pitch Black Build & Battle Box (ID: 885540) — Pokémon Box Set, rank 20, score 0.4348

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** "Rip & Ship" is the same service pattern as a box break — the seller opens packs on a scheduled date and ships the loose cards. The trailing date is the event, and 3.90 EUR is a per-slot price, not a product price.

**Why candidates didn't match:**
- Pitch Black Booster Box: the sealed box the seller rips open; never shipped to the customer
- Pitch Black Booster: a sealed single pack; this service ships opened cards instead
- Pitch Black Booster Box (18 Boosters): as above, and the listing gives no pack count
- Pitch Black Elite Trainer Box: no ETB is mentioned — matched on "Pitch Black" alone
- Pitch Black Build & Battle Box: likewise matched on the set name only

---

## Example 11

**raw_name:** `Pokemon Paldean Fates Tech Sticker Collection Case (12)`

**Sites:** God of Cards  ·  **Observed price:** 949.11 EUR

**Candidates shown:**
1. Paldean Fates: Tech Sticker Collection Display (ID: 756233) — Pokémon Blisters, rank 146, score 0.7723
2. Paldean Fates: Fidough Tech Sticker Collection (ID: 745545) — Pokémon Blisters, rank 87, score 0.7327
3. Paldean Fates: Greavard Tech Sticker Collection (ID: 745547) — Pokémon Blisters, rank 72, score 0.7255
4. Paldean Fates: Maschiff Tech Sticker Collection (ID: 745546) — Pokémon Blisters, rank 78, score 0.7255
5. Ascended Heroes: Tech Sticker Collection Display (ID: 860564) — Pokémon Blisters, rank 117, score 0.6408

**Chosen mapping:** Paldean Fates: Greavard Tech Sticker Collection (ID: 745547) — **undecided**, best guess only

**Status:** `undecided`

**Why it matched:** Set and product line are certain, and 949.11 EUR is consistent with 12 units at roughly 79 EUR each. But a case of 12 holds an assortment of the three per-Pokémon collections (Greavard, Maschiff, Fidough) and the listing names none of them, so rule 2 takes precedence over rule 3 and this stays `undecided`. Best guess is the lowest-ranked single collection, per rule 2 — not the Display row, because rule 3 asks for the single-unit row even when the listing is a case.

**Why candidates didn't match:**
- Paldean Fates: Tech Sticker Collection Display: Cardmarket's own multi-unit SKU; rule 3 asks for the single unit, so the Display is not the right target even for a case of 12
- Paldean Fates: Fidough Tech Sticker Collection: one of three possible contents
- Paldean Fates: Greavard Tech Sticker Collection: the recorded best guess — lowest rank of the three, but still a guess at which variant the case holds
- Paldean Fates: Maschiff Tech Sticker Collection: likewise — three equally plausible variants is exactly what makes this undecided
- Ascended Heroes: Tech Sticker Collection Display: correct product line, wrong set

---

## Example 12

**raw_name:** `PokemonLeague Battle DeckShadow Rider / Ice RiderBooster Box (6)`

**Sites:** God of Cards  ·  **Observed price:** 158.14 EUR

**Candidates shown:**
1. Chilling Reign: Pokémon Center Shadow Rider Calyrex Elite Trainer Box (ID: 567356) — Pokémon Elite Trainer Boxes, rank 134, score 0.5113
2. Battle Partners Booster Box (ID: 804827) — Pokémon Display, rank 43, score 0.5055
3. Battle Partners Booster Box Case (ID: 804830) — Pokémon Display, rank 179, score 0.5
4. CSM1.5C: Battle Elite Booster Box (ID: 800327) — Pokémon Display, rank 229, score 0.4948
5. CS6aC: Azure Shadow - Roar Booster Box (ID: 787552) — Pokémon Display, rank 221, score 0.4902

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** Two problems at once. It is a random Shadow Rider / Ice Rider assortment, and `Booster Box (6)` is this retailer's wrapper for a 6-unit case of League Battle Decks — the words "Booster Box" do not denote a booster box here. 158.14 EUR is about six battle decks, not a booster box. The random-assortment rule alone is enough to null it.

**Why candidates didn't match:**
- Chilling Reign: Pokémon Center Shadow Rider Calyrex Elite Trainer Box: right Pokémon but an Elite Trainer Box rather than a League Battle Deck, and the Pokémon Center edition
- Battle Partners Booster Box: matched "Battle" and "Booster Box"; an unrelated Japanese set
- Battle Partners Booster Box Case: same wrong set, and a case
- CSM1.5C: Battle Elite Booster Box: matched "Battle"; a Simplified Chinese set
- CS6aC: Azure Shadow - Roar Booster Box: matched "Shadow"; a Simplified Chinese set

---

## Example 13

**raw_name:** `PokémonUltra Pro Charmander M2 Deck Box`

**Sites:** MaxGaming  ·  **Observed price:** 42.90 EUR

**Candidates shown:**
1. Pokémon Center Hiroshima Special Box (ID: 830071) — Pokémon Box Set, rank 21, score 0.56
2. Pokémon Center Tohoku Special Box (ID: 830070) — Pokémon Box Set, rank 24, score 0.5556
3. Pokémon Center Fukuoka Special Box (ID: 830072) — Pokémon Box Set, rank 18, score 0.5479
4. Pokémon GO Card File Set (ID: 653673) — Pokémon Box Set, rank 87, score 0.5397
5. Pokémon Card 151 Booster Box (ID: 718514) — Pokémon Display, rank 23, score 0.5373

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** An Ultra Pro deck box is a rigid plastic storage accessory holding no cards, so it falls outside the eight in-scope categories. "Deck Box" is a false friend: it is neither a Theme Deck nor a Box Set.

**Why candidates didn't match:**
- Pokémon Center Hiroshima Special Box: a sealed card product; matched on the word "Box" alone
- Pokémon Center Tohoku Special Box: same — a sealed Pokémon Center box, not storage
- Pokémon Center Fukuoka Special Box: same
- Pokémon GO Card File Set: also storage-adjacent, but a sealed product that includes cards
- Pokémon Card 151 Booster Box: a 36-pack display; matched on "Box"

---

## Example 14

**raw_name:** `Keräilykansio ja korttipakka Pokemon`

**Sites:** Muovi ja Lelu  ·  **Observed price:** 12.90 EUR

**Candidates shown:**
1. 2025 Stacking Tin: Paradox Pokémon (ID: 804348) — Pokémon Tins, rank 161, score 0.4571
2. Guardians Rising: Lurantis 1-Pack Blister (ID: 586001) — Pokémon Blisters, rank 199, score 0.3896
3. V Strikers Tins: Tyranitar V Tin (ID: 547846) — Pokémon Tins, rank 181, score 0.3824
4. Pokémon GO Enhanced Expansion Pack Promo Booster (ID: 666447) — Pokémon Booster, rank 118, score 0.381
5. Art Illustration Celebration: Poké Ball Tin (ID: 853941) — Pokémon Tins, rank 85, score 0.3797

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** Finnish for "collector binder and card pack". Binders are accessories and out of scope, the bundled cards are unspecified, and no set is named anywhere — 12.90 EUR is a toy-shop binder bundle.

**Why candidates didn't match:**
- 2025 Stacking Tin: Paradox Pokémon: a tin, not a binder, and the listing names no set
- Guardians Rising: Lurantis 1-Pack Blister: a blister from a 2017 set, unrelated
- V Strikers Tins: Tyranitar V Tin: a tin, unrelated
- Pokémon GO Enhanced Expansion Pack Promo Booster: a booster, unrelated
- Art Illustration Celebration: Poké Ball Tin: a tin, unrelated — all five matched on little more than "Pokemon"

---

## Example 15

**raw_name:** `Elite Trainer Box Phantasmal Flames`

**Sites:** Fantasialinna  ·  **Observed price:** 149.00 EUR

**Candidates shown:**
1. 151 10 Elite Trainer Box Case (ID: 719692) — Pokémon Elite Trainer Boxes, rank 143, score 0.6562
2. Sun & Moon Elite Trainer Box (Lunala) (ID: 295477) — Pokémon Elite Trainer Boxes, rank 98, score 0.6111
3. 151 Elite Trainer Box (ID: 719691) — Pokémon Elite Trainer Boxes, rank 29, score 0.6071
4. Sun & Moon Elite Trainer Box (Solgaleo) (ID: 294123) — Pokémon Elite Trainer Boxes, rank 62, score 0.5946
5. Black Bolt 10 Elite Trainer Box Case (ID: 824090) — Pokémon Elite Trainer Boxes, rank 86, score 0.5915

**Chosen mapping:** Phantasmal Flames Elite Trainer Box (ID: 846744) — **mapped**

**Status:** `mapped`

**Why it matched:** Word order is inverted relative to Cardmarket's "<Set> Elite Trainer Box", which is why every string-similarity candidate is wrong, but set and type are both unambiguous. Default to the plain retail edition over the Pokémon Center one. Worth flagging: at 149.00 EUR this is well above a normal ETB, and the Pokémon Center variant (ID 846743, rank 2) is the pricier edition — so price alone would argue the other way. The set is heavily scalped, and a Finnish general retailer stocking a Pokémon Center exclusive would be unusual, so the plain edition still wins.

**Why candidates didn't match:**
- 151 10 Elite Trainer Box Case: wrong set and a 10-unit case
- Sun & Moon Elite Trainer Box (Lunala): wrong set entirely — a 2017 ETB
- 151 Elite Trainer Box: wrong set
- Sun & Moon Elite Trainer Box (Solgaleo): wrong set, and the other Sun & Moon legendary variant
- Black Bolt 10 Elite Trainer Box Case: wrong set and a 10-unit case

---

## Example 16

**raw_name:** `PokÃ©mon Prismatic Evolution boosteri`

**Sites:** Muksumassi  ·  **Observed price:** 20.95 EUR

**Candidates shown:**
1. Prismatic Evolutions Booster (ID: 798923) — Pokémon Booster, rank 7, score 0.8308
2. Prismatic Evolutions Booster Bundle (ID: 798924) — Pokémon Display, rank 10, score 0.75
3. Prismatic Evolutions Booster Bundle Display (ID: 798925) — Pokémon Display, rank 91, score 0.7
4. Prismatic Evolutions Poster Collection (ID: 798946) — Pokémon Box Set, rank 28, score 0.6933
5. Mega Evolution Booster (ID: 834829) — Pokémon Booster, rank 10, score 0.678

**Chosen mapping:** Prismatic Evolutions Booster (ID: 798923) — **mapped**

**Status:** `mapped`

**Why it matched:** `PokÃ©mon` is UTF-8 read as Latin-1 — mechanical damage to a single character, not unreadable text, so this does **not** qualify as `undecided`. The rest identifies the set (singular "Evolution" in the listing vs plural "Evolutions" in the catalog) and `boosteri` is Finnish for one booster pack. Note that 20.95 EUR is high for a single pack; this set is heavily scalped, which is why price is a useful prior but never a hard rule.

**Why candidates didn't match:**
- Prismatic Evolutions Booster: this is the chosen row
- Prismatic Evolutions Booster Bundle: a 6-pack bundle rather than the single pack "boosteri" denotes
- Prismatic Evolutions Booster Bundle Display: a display of bundles, further still from a single pack
- Prismatic Evolutions Poster Collection: correct set but a poster collection, not cards
- Mega Evolution Booster: matched on "Evolution"; Mega Evolution is a different set

---

## Example 17

**raw_name:** `Pokemon Deck Champ World`

**Sites:** JR Kodintavaratalo  ·  **Observed price:** 32.95 EUR

**Candidates shown:**
1. Pokémon GO Card File Set (ID: 653673) — Pokémon Box Set, rank 87, score 0.5
2. Pokémon GO: Special Collection—Team Valor (ID: 653707) — Pokémon Box Set, rank 153, score 0.4923
3. Pokémon Trading Card Game Classic (ID: 737598) — Pokémon Box Set, rank 69, score 0.4912
4. Pokémon GO: Pikachu Tin (ID: 653742) — Pokémon Tins, rank 14, score 0.4681
5. Pokémon GO: Snorlax Tin (ID: 653711) — Pokémon Tins, rank 31, score 0.4681

**Chosen mapping:** `none` — **undecided** (no defensible best guess)

**Status:** `undecided`

**Why it matched:** Almost certainly a World Championship deck — 32.95 EUR fits one — but the catalog holds 29 `WCD` rows spanning 2017 to 2025 and this listing gives neither a year nor a player name. With 29 equally plausible rows there is no defensible best guess, so the product id is left empty — the one case in this bank where rule 2's "lowest-rank variant" guess would be meaningless.

**Why candidates didn't match:**
- Pokémon GO Card File Set: matched on nothing but "Pokémon" and a card-storage association
- Pokémon GO: Special Collection—Team Valor: a Pokémon GO collection box, unrelated
- Pokémon Trading Card Game Classic: a standalone boxed game, not a Championship deck
- Pokémon GO: Pikachu Tin: a tin, unrelated
- Pokémon GO: Snorlax Tin: a tin, unrelated

---

## Example 18

**raw_name:** `Topps Formula 1 Turbo Attax Eco Box 2025`

**Sites:** Karkkainen.com verkkokauppa  ·  **Observed price:** 7.19 EUR

**Candidates shown:**
1. Blastoise VMAX Battle Box (ID: 546841) — Pokémon Box Set, rank 266, score 0.4923
2. Lost Origin Build & Battle Box (ID: 666148) — Pokémon Box Set, rank 223, score 0.4857
3. Chaos Rising Build & Battle Box (ID: 877282) — Pokémon Box Set, rank 110, score 0.4789
4. Perfect Order Build & Battle Box (ID: 865397) — Pokémon Box Set, rank 59, score 0.4722
5. Temporal Forces 6 Booster Box Case (ID: 750407) — Pokémon Display, rank 144, score 0.4595

**Chosen mapping:** `none` — **null_mapped**

**Status:** `null_mapped`

**Why it matched:** Topps Formula 1 Turbo Attax is a motorsport sticker/card line with no connection to the Pokémon TCG. Non-Pokémon trading cards are out of scope regardless of how closely the packaging words resemble a Pokémon product.

**Why candidates didn't match:**
- Blastoise VMAX Battle Box: a Pokémon battle box; matched on "Box"
- Lost Origin Build & Battle Box: a Pokémon build & battle box; matched on "Box"
- Chaos Rising Build & Battle Box: same, different set
- Perfect Order Build & Battle Box: same, different set
- Temporal Forces 6 Booster Box Case: a Pokémon booster box case; "Forces" is a coincidental echo of "Formula"

---

## Example 19

**raw_name:** `Scarlet &amp; Violet: Paradox Rift booster`

**Sites:** Peliparatiisi  ·  **Observed price:** 4.90 EUR

**Candidates shown:**
1. Scarlet & Violet Booster (ID: 692088) — Pokémon Booster, rank 29, score 0.7273
2. Scarlet & Violet Sleeved Booster (ID: 692091) — Pokémon Booster, rank 238, score 0.7027
3. Scarlet & Violet: Espathra 1-Pack Blister (ID: 692408) — Pokémon Blisters, rank 154, score 0.6988
4. Scarlet & Violet Booster Box (ID: 692092) — Pokémon Display, rank 66, score 0.6857
5. Scarlet & Violet 6 Booster Box Case (ID: 692095) — Pokémon Display, rank 194, score 0.6494

**Chosen mapping:** Paradox Rift Booster (ID: 728716) — **mapped**

**Status:** `mapped`

**Why it matched:** `Scarlet &amp; Violet` is an un-decoded HTML entity naming the **era**, not the set; the actual set is Paradox Rift, and Cardmarket names sets without the era prefix. Bare "booster" plus a 4.90 EUR price means the single pack. **All five candidates are Scarlet & Violet base-set rows** — the era prefix dominated the string score and pushed the correct row out of the top five entirely, which is the clearest example in this bank of why the retailer prefix must be stripped before matching.

**Why candidates didn't match:**
- Scarlet & Violet Booster: the era prefix matched, but the base set is a different release from Paradox Rift
- Scarlet & Violet Sleeved Booster: wrong set and a sleeved pack
- Scarlet & Violet: Espathra 1-Pack Blister: wrong set and a blister
- Scarlet & Violet Booster Box: wrong set and a display box
- Scarlet & Violet 6 Booster Box Case: wrong set and a 6-box case

---

## Example 20

**raw_name:** `PokémonScarlet & Violet 10: Destined Rivals Booster`

**Sites:** MaxGaming  ·  **Observed price:** 7.29 EUR

**Candidates shown:**
1. Scarlet & Violet Sleeved Booster (ID: 692091) — Pokémon Booster, rank 238, score 0.6747
2. Scarlet & Violet 10 Elite Trainer Box Case (ID: 692105) — Pokémon Elite Trainer Boxes, rank 75, score 0.6667
3. Gym Promo Scarlet & Violet Have Fun Spring 2022 Booster (ID: 843809) — Pokémon Booster, rank 221, score 0.6415
4. Pokémon Card Gym Promo Scarlet & Violet Vol. 10 Booster (ID: 821706) — Pokémon Booster, rank 239, score 0.6415
5. Scarlet & Violet Booster (ID: 692088) — Pokémon Booster, rank 29, score 0.64

**Chosen mapping:** Destined Rivals Booster (ID: 818570) — **mapped**

**Status:** `mapped`

**Why it matched:** This retailer concatenates the brand with no separator and includes both the era and its set number (`Scarlet & Violet 10`). Strip both; Destined Rivals is the set. Bare "Booster" at 7.29 EUR is the single pack. Contrast with example 22, the same set at 389.50 EUR.

**Why candidates didn't match:**
- Scarlet & Violet Sleeved Booster: matched the era prefix; the base set and a sleeved pack
- Scarlet & Violet 10 Elite Trainer Box Case: matched "Scarlet & Violet 10" literally, but this is a 10-unit ETB case of the base set
- Gym Promo Scarlet & Violet Have Fun Spring 2022 Booster: a 2022 Gym promo booster, unrelated
- Pokémon Card Gym Promo Scarlet & Violet Vol. 10 Booster: "Vol. 10" is a Japanese Gym promo series, not set number 10
- Scarlet & Violet Booster: the base-set single pack rather than Destined Rivals

---

## Example 21

**raw_name:** `Pokemon Keräilykortit Chaos Rising Boosterpakkaus`

**Sites:** Casagrande  ·  **Observed price:** 6.50 EUR

**Candidates shown:**
1. Chaos Rising Booster (ID: 877296) — Pokémon Booster, rank 4, score 0.5797
2. Chaos Rising Booster Bundle (ID: 877284) — Pokémon Display, rank 15, score 0.5526
3. Chaos Rising 6 Booster Box Case (ID: 877281) — Pokémon Display, rank 120, score 0.55
4. Chaos Rising Booster Box (ID: 877295) — Pokémon Display, rank 14, score 0.5479
5. Chaos Rising Sleeved Booster (ID: 877292) — Pokémon Booster, rank 43, score 0.5195

**Chosen mapping:** Chaos Rising Booster (ID: 877296) — **mapped**

**Status:** `mapped`

**Why it matched:** `Keräilykortit` ("trading cards") is generic retailer filler and `Boosterpakkaus` is a single booster pack, confirmed by the 6.50 EUR price. Same decision as example 2 reached from Finnish rather than a set code.

**Why candidates didn't match:**
- Chaos Rising Booster: this is the chosen row
- Chaos Rising Booster Bundle: a 6-pack bundle, not one pack
- Chaos Rising 6 Booster Box Case: a 6-box case
- Chaos Rising Booster Box: the 36-pack display box — roughly 30x the listed price
- Chaos Rising Sleeved Booster: a sleeved pack, which the listing does not mention

---

## Example 22

**raw_name:** `Destined Rivals Booster laatikko`

**Sites:** Porvoon Pelikauppa  ·  **Observed price:** 389.50 EUR

**Candidates shown:**
1. Destined Rivals Booster Box (ID: 818574) — Pokémon Display, rank 9, score 0.8475
2. Destined Rivals Booster (ID: 818570) — Pokémon Booster, rank 1, score 0.8364
3. Destined Rivals Booster Bundle (ID: 818578) — Pokémon Display, rank 24, score 0.8065
4. Destined Rivals 6 Booster Box Case (ID: 818576) — Pokémon Display, rank 97, score 0.7576
5. Destined Rivals Sleeved Booster (ID: 818573) — Pokémon Booster, rank 44, score 0.7302

**Chosen mapping:** Destined Rivals Booster Box (ID: 818574) — **mapped**

**Status:** `mapped`

**Why it matched:** `laatikko` is Finnish for box, so this is the 36-pack display and not the single pack — the 389.50 EUR price confirms it. The single "Destined Rivals Booster" sits at popularity rank 1 against the box's rank 9, so a naive popularity prior would pick the pack; the Finnish product-type word overrides the prior.

**Why candidates didn't match:**
- Destined Rivals Booster Box: this is the chosen row
- Destined Rivals Booster: the single pack — rank 1 makes it the popularity default, but 389.50 EUR rules it out
- Destined Rivals Booster Bundle: a 6-pack bundle, far below the listed price
- Destined Rivals 6 Booster Box Case: a 6-box case, far above it
- Destined Rivals Sleeved Booster: a sleeved single pack

---

## Example 23

**raw_name:** `Pokemon Lumiose City Mini Tin`

**Sites:** Casagrande  ·  **Observed price:** 14.90 EUR

**Candidates shown:**
1. Pokémon GO: Blissey Mini Tin (ID: 653713) — Pokémon Tins, rank 15, score 0.7368
2. Lumiose City: Emboar Mini Tin (ID: 878508) — Pokémon Tins, rank 64, score 0.7241
3. Lumiose City: Mini Tin Display (ID: 878511) — Pokémon Tins, rank 10, score 0.7119
4. Lumiose City: Gallade Mini Tin (ID: 878510) — Pokémon Tins, rank 33, score 0.7119
5. Lumiose City: Meganium Mini Tin (ID: 878507) — Pokémon Tins, rank 37, score 0.7

**Chosen mapping:** Lumiose City: Feraligatr Mini Tin (ID: 878509) — **undecided**, best guess only

**Status:** `undecided`

**Why it matched:** Set and product type are certain and the 14.90 EUR price matches one mini tin, which usefully rules out the Mini Tin Display (a multi-unit row costing roughly ten times as much). But Cardmarket lists five per-Pokémon Lumiose City mini tins and the listing names none, so the unnamed-variant rule applies; the lowest-ranked single tin is recorded as the best guess.

**Why candidates didn't match:**
- Pokémon GO: Blissey Mini Tin: a mini tin but from an unrelated set
- Lumiose City: Emboar Mini Tin: correct set and type, but assumes Emboar
- Lumiose City: Mini Tin Display: correct set, but a multi-unit display that the 14.90 EUR price excludes
- Lumiose City: Gallade Mini Tin: correct set and type, but assumes Gallade
- Lumiose City: Meganium Mini Tin: correct set and type, but assumes Meganium — five equal options means undecided

---

## Example 24

**raw_name:** `Pokémon TCG: ME05 Pitch Black Booster Box (MAX 1 kpl/asiakas)`

**Sites:** PokePulls  ·  **Observed price:** 199.90 EUR

**Candidates shown:**
1. Pitch Black Booster Box (18 Boosters) (ID: 885544) — Pokémon Display, rank 59, score 0.5918
2. Pitch Black 6 Booster Box Case (ID: 885528) — Pokémon Display, rank 65, score 0.5714
3. Pitch Black Booster Box (ID: 885545) — Pokémon Display, rank 1, score 0.5476
4. Pokémon GO Enhanced Expansion Pack Booster Box (ID: 664310) — Pokémon Display, rank 107, score 0.5234
5. Pokémon Card 151 Booster Box (ID: 718514) — Pokémon Display, rank 23, score 0.5169

**Chosen mapping:** Pitch Black Booster Box (ID: 885545) — **mapped**

**Status:** `mapped`

**Why it matched:** `(MAX 1 kpl/asiakas)` is a per-customer purchase limit — pure retailer noise to be stripped. `ME05` and "Pitch Black" are both stated and agree, and "Booster Box" is explicit, so this is the standard 36-pack display; 199.90 EUR matches the 36-pack rather than the 18-pack variant that topped the candidate list.

**Why candidates didn't match:**
- Pitch Black Booster Box (18 Boosters): the half-size 18-pack box; unqualified "Booster Box" means the standard 36 and the price agrees
- Pitch Black 6 Booster Box Case: a 6-box case, roughly six times the listed price
- Pitch Black Booster Box: this is the chosen row
- Pokémon GO Enhanced Expansion Pack Booster Box: wrong set entirely
- Pokémon Card 151 Booster Box: wrong set — the Japanese 151 box

---

## Example 25

**raw_name:** `Pokemon Collector's Chest Fall 2025`

**Sites:** Fantasialinna  ·  **Observed price:** 49.90 EUR

**Candidates shown:**
1. Pokémon TCG 2023 Collector Chest (ID: 709528) — Pokémon Box Set, rank 103, score 0.6567
2. Celebrations Collector Chest (ID: 570908) — Pokémon Box Set, rank 92, score 0.6032
3. Spring 2021 Collector Chest (ID: 546846) — Pokémon Tins, rank 164, score 0.5806
4. Spring 2017 Collector Chest (ID: 371779) — Pokémon Tins, rank 214, score 0.5806
5. Spring 2018 Collector Chest (ID: 371780) — Pokémon Tins, rank 236, score 0.5806

**Chosen mapping:** Fall 2025 Collector Chest (ID: 845850) — **mapped**

**Status:** `mapped`

**Why it matched:** Word-order inversion plus an apostrophe Cardmarket omits: the listing's "Collector's Chest Fall 2025" is the catalog's "Fall 2025 Collector Chest". Season plus year identifies the row uniquely, and 49.90 EUR is the normal price for a collector chest. The correct row is absent from the top five because every candidate shares the "Collector Chest" tail while differing on the season prefix.

**Why candidates didn't match:**
- Pokémon TCG 2023 Collector Chest: a 2023 chest — right product line, wrong year
- Celebrations Collector Chest: the Celebrations chest, a different release
- Spring 2021 Collector Chest: Spring 2021, wrong season and year
- Spring 2017 Collector Chest: Spring 2017, wrong season and year
- Spring 2018 Collector Chest: Spring 2018, wrong season and year

---
