"""Heuristic canonical-name generator for the normalisation runbook.

See docs/normalisation-runbook.md step 2. Reads a `pending_names.json` export
(from `python -m scraper.normaliser export`) and writes a `mappings.json`
suitable for `python -m scraper.normaliser import`, using:

- a curated list of known Pokémon TCG expansion / product-line names (SET_NAMES,
  plus special-cases for the 2026 "Mega Evolution" sub-sets and the
  "First Partner Illustration Collection" series)
- regex-based sealed-product-type detection (TYPE_PATTERNS)
- a merch/non-sealed-product skip-list (SKIP_KEYWORDS) so plush, figures, Funko
  Pops, binders, sleeves, apparel etc. are deliberately left unmapped rather
  than given a bogus canonical name

Only entries the heuristics are confident about get a canonical_name. Everything
else is left out of mappings.json on purpose -- re-running `export` afterward
still shows them as Unknown, ready for a future incremental pass once this
script's tables are extended (new sets, new SKIP_KEYWORDS, etc.).

Usage:
    venv/bin/python scripts/build_canonical_mappings.py [pending_names.json]
        [--mappings-out mappings.json]
        [--dump-skipped-dir /tmp/norm]   # optional: write skipped_merch.txt /
                                          # skipped_no_match.txt there for review
"""
import argparse
import json
import re
from collections import Counter

# Known official (or clearly-identifiable) Pokémon TCG expansion / product-line names.
# Ordered longest-first so more specific names win over generic substrings.
# Extend this list as new expansions release.
SET_NAMES = [
    "Scarlet & Violet 151", "Scarlet and Violet 151",
    "Prismatic Evolutions", "Paldea Evolved", "Obsidian Flames",
    "Paradox Rift", "Paradoxrift", "Temporal Forces", "Twilight Masquerade",
    "Shrouded Fable", "Stellar Crown", "Surging Sparks", "Journey Together",
    "Destined Rivals", "Black Bolt", "White Flare", "Paldean Fates",
    "Silver Tempest", "Crown Zenith", "Lost Origin", "Astral Radiance",
    "Brilliant Stars", "Fusion Strike", "Chilling Reign", "Evolving Skies",
    "Celebrations", "Darkness Ablaze",
    # Japanese / S-Chinese exclusive expansions seen in past exports
    "Stellar Crystal", "Brilliant Illusions", "Gem Pack Vol. 2", "Gem Pack Vol. 4",
    "Gem Pack Vol. 5", "Collect 151 Surprises", "Collect 151 Hope", "Eternal Birth",
    "Violet EX", "Star Birth", "Incandescent Arcana", "Shocking Volt Tackle",
    "Future Flash", "Dark Phantasma", "Super Electric Breaker", "Magnetic Coin Set Paldea",
    "Pokémon GO", "Pokemon GO", "Pokemon Go",
    "Scarlet & Violet", "Scarlet and Violet",
    "Sword & Shield", "Sun & Moon",
]

# Spelling/typo variants that should collapse to one canonical spelling.
SET_NAME_ALIASES = {
    "paradoxrift": "Paradox Rift",
    "scarlet and violet 151": "Scarlet & Violet 151",
    "scarlet and violet": "Scarlet & Violet",
    "pokemon go": "Pokémon GO",
    "pokémon go": "Pokémon GO",
    "151": "Scarlet & Violet 151",
}

SV_ERA_RE = re.compile(r"scarlet\s*(&|and)\s*violet", re.IGNORECASE)
SV151_RE = re.compile(r"\b151\b")
FIRST_PARTNER_RE = re.compile(r"first partner")
SERIES_RE = re.compile(r"series\s*(\d+)")

# Mega Evolution sub-set codenames (2026 "Mega Evolution" TCG series) and their codes.
# Add new sub-sets here as ME06+ releases.
ME_SUBSET_NAMES = ["Pitch Black", "Chaos Rising", "Perfect Order", "Ascended Heroes"]
ME_CODE_TO_SUBSET = {
    "me05": "Pitch Black",
    "me04": "Chaos Rising",
    "me03": "Perfect Order",
    "me02.5": "Ascended Heroes",
    "me02,5": "Ascended Heroes",
}
ME_CODE_RE = re.compile(r"\bme0?(2\.5|2,5|3|4|5)\b")

# "<... anything> - <Subset Name> (<CODE>) - Booster ..." — Japanese/Chinese exclusive
# print runs are usually labelled with their own subset name in parentheses; prefer
# that specific subset over a generic era name like "Scarlet & Violet".
BRACKET_SUBSET_RE = re.compile(
    r"-\s*([A-Za-z0-9&'.,\s]+?)\s*\(([A-Z0-9.]{2,10})\)\s*-\s*booster", re.IGNORECASE
)

# Product-type patterns, checked in order (most specific first).
TYPE_PATTERNS = [
    (r"premium\s*checklane\s*blister", "Checklane Blister"),
    (r"checklane\s*blister|checklane\b", "Checklane Blister"),
    (r"premium\s*collection", "Premium Collection Box"),
    (r"collector'?s?\s*chest", "Collector's Chest"),
    (r"illustration\s*collection", "Illustration Collection"),
    (r"pin\s*collection", "Pin Collection"),
    (r"tech\s*sticker\s*collection", "Tech Sticker Collection"),
    (r"gift\s*box", "Gift Box"),
    (r"\b\d+[- ]?pack\s*blister", "Multi-Pack Blister"),
    (r"\bblister", "Blister Pack"),
    (r"elite\s*trainer\s*box|\betb\b", "Elite Trainer Box"),
    (r"top\s*trainer\s*box", "Top Trainer Box"),
    (r"build\s*&?\s*battle\s*box", "Build & Battle Box"),
    (r"deck\s*build\s*box", "Deck Build Box"),
    (r"mini\s*tin", "Mini Tin"),
    (r"\btin\b", "Tin"),
    (r"booster\s*bundle", "Booster Bundle"),
    (r"booster\s*(display|box)|(\d+)[- ]?(pack|kpl)\s*booster\s*box|booster\s*box\s*\(\d+\s*boxes?\)", "Booster Box"),
    (r"world\s*championships?\s*deck", "World Championships Deck"),
    (r"league\s*battle\s*deck", "League Battle Deck"),
    (r"battle\s*deck", "Battle Deck"),
    (r"starter\s*set", "Starter Set"),
    (r"\b(ex|v-union|vmax|vstar|v)?\s*collection\b", "Collection Box"),
    (r"boosteri?p?a?k?k?a?u?s?|\bbooster\b|\bbooster\s*\d*\s*kpl\b", "Booster Pack"),
]

# Keywords that mean "this is merch, not a sealed TCG product" -> skip (leave unmapped).
SKIP_KEYWORDS = [
    "pehmolelu", "pehmo", "plush", "squishmallow", "figuuri", "figure", "funko",
    "kansio", "binder", "portfolio", "sleeve", "suoja", "toploader", "reppu", "naamiaisasu",
    "palapeli", "puzzle", "rannekello", "watch", "spinner", "clip'n'go", "clip 'n' go",
    "clip-on", "maskotti", "rakennussetti", "construx", "joulukalenteri", "calendar",
    "battle academy", "keychain", "avaimenper", "vyösetti", "vyö ", "laukku",
    "grinch", "penny sleeve", "case (", "random selection", "vyöllä",
    "special card set", "v-union", "lego ", "topps", "magic the gathering",
    "single card", "reverse holo", "hologrammipeli", "takara tomy",
    "#", "– skyridge", "holomonsters", "deck box",
]


def find_type(name_lower: str):
    for pattern, label in TYPE_PATTERNS:
        if re.search(pattern, name_lower):
            return label
    return None


def find_set(name: str):
    for s in SET_NAMES:
        if s.lower() in name.lower():
            return SET_NAME_ALIASES.get(s.lower(), s)
    return None


def detect_me_subset(low: str):
    for name in ME_SUBSET_NAMES:
        if name.lower() in low:
            return name
    m = ME_CODE_RE.search(low)
    if m:
        code = "me0" + m.group(1)
        return ME_CODE_TO_SUBSET.get(code)
    return None


def build_mappings(entries):
    mapped = []
    skipped_merch = []
    skipped_no_match = []

    for entry in entries:
        raw = entry["raw_name"]
        low = raw.lower()

        if any(k in low for k in SKIP_KEYWORDS):
            skipped_merch.append(raw)
            continue

        if FIRST_PARTNER_RE.search(low):
            series_match = SERIES_RE.search(low)
            if series_match:
                canonical = f"First Partner Illustration Collection — Series {series_match.group(1)}"
            else:
                canonical = "First Partner Illustration Collection"
            mapped.append({"raw_name": raw, "canonical_name": canonical})
            continue

        ptype = find_type(low)
        if not ptype:
            skipped_no_match.append(raw)
            continue

        me_subset = detect_me_subset(low)
        if me_subset:
            set_name = f"Mega Evolution: {me_subset}"
        else:
            bracket_match = BRACKET_SUBSET_RE.search(raw)
            if bracket_match:
                subset = bracket_match.group(1).strip(" -")
                set_name = SET_NAME_ALIASES.get(subset.lower(), subset)
            elif SV_ERA_RE.search(low) and SV151_RE.search(low):
                set_name = "Scarlet & Violet 151"
            else:
                set_name = find_set(raw)

        if not set_name:
            skipped_no_match.append(raw)
            continue

        mapped.append({"raw_name": raw, "canonical_name": f"{set_name} — {ptype}"})

    return mapped, skipped_merch, skipped_no_match


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default="pending_names.json")
    parser.add_argument("--mappings-out", default="mappings.json")
    parser.add_argument("--dump-skipped-dir", default=None, help="Directory to write skipped_merch.txt / skipped_no_match.txt for review")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        entries = json.load(f)

    mapped, skipped_merch, skipped_no_match = build_mappings(entries)

    print(f"mapped: {len(mapped)}")
    print(f"skipped (merch/non-sealed): {len(skipped_merch)}")
    print(f"skipped (no confident set/type match): {len(skipped_no_match)}")

    with open(args.mappings_out, "w", encoding="utf-8") as f:
        json.dump(mapped, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {args.mappings_out}")

    if args.dump_skipped_dir:
        import os
        os.makedirs(args.dump_skipped_dir, exist_ok=True)
        with open(os.path.join(args.dump_skipped_dir, "skipped_merch.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(skipped_merch))
        with open(os.path.join(args.dump_skipped_dir, "skipped_no_match.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(skipped_no_match))
        print(f"wrote skipped_merch.txt / skipped_no_match.txt to {args.dump_skipped_dir}")

    c = Counter(m["canonical_name"] for m in mapped)
    print(f"\nunique canonical products: {len(c)}")


if __name__ == "__main__":
    main()
