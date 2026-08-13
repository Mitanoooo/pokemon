#!/usr/bin/env python3
"""Score curated catalog products against a raw_name for the calibration session.

Implements the step-3 scoring rule from ``copilot_prompts/llm_calibrate.md``:
difflib ratio on lowercased names, ``popularity_rank`` ascending as tiebreaker.

The curated catalog is read from a JSONL dump (one ``{"id","name","category",
"rank"}`` object per line) so the session does not re-query Hetzner per name::

    ssh ... "python -c '...SELECT id, name, category_name, popularity_rank
        FROM cardmarket_products WHERE is_curated = 1...'" > curated.jsonl

Usage::

    python scripts/calibration_candidates.py curated.jsonl "Pitch Black Booster Box"
    python scripts/calibration_candidates.py curated.jsonl --file names.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

TOP_N = 5
HINT_N = 8

# Words that carry no discriminating signal for the token-overlap hint list --
# they appear in most raw_names, most catalog names, or both.
NOISE_TOKENS = frozenset(
    """
    pokemon pokémon tcg the of and a s pcs kpl st box pack packs
    """.split()
)

# Retailer set-code abbreviations -> the expansion they denote. Cardmarket names
# the expansion, retailers often ship only the code (Prisma's "Poke ME05 ...").
SET_CODES = {
    "me01": "Mega Evolution",
    "me1": "Mega Evolution",
    "me02": "Phantasmal Flames",
    "me2": "Phantasmal Flames",
    "me025": "Ascended Heroes",
    "me03": "Perfect Order",
    "me3": "Perfect Order",
    "me04": "Chaos Rising",
    "me4": "Chaos Rising",
    "me05": "Pitch Black",
    "me5": "Pitch Black",
    "sv10": "Destined Rivals",
    "sv9": "Journey Together",
    "sv8": "Surging Sparks",
    "sv7": "Stellar Crown",
    "sv6": "Twilight Masquerade",
    "sv5": "Temporal Forces",
    "sv4": "Paradox Rift",
    "sv3": "Obsidian Flames",
    "sv2a": "151",
    "sv11b": "Black Bolt",
    "sv11w": "White Flare",
    "m5": "Abyss Eye",
    "m2": "Inferno X",
    "bst": "Booster",
}


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in NOISE_TOKENS}


def expand_codes(tokens: set[str]) -> set[str]:
    """Add the expansion name behind any retailer set-code in ``tokens``."""
    extra: set[str] = set()
    for t in tokens:
        if t in SET_CODES:
            extra |= tokenize(SET_CODES[t])
    return tokens | extra


def load_catalog(path: Path) -> list[dict]:
    products = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    if not products:
        sys.exit(f"{path}: no products loaded")
    return products


def top_candidates(raw_name: str, products: list[dict], top_n: int = TOP_N) -> list[dict]:
    needle = raw_name.lower()
    scored = []
    for p in products:
        ratio = SequenceMatcher(None, needle, p["name"].lower()).ratio()
        # lower rank = more popular, so it sorts ascending as the tiebreaker
        scored.append((-ratio, p["rank"] if p["rank"] is not None else 10**9, p, ratio))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [dict(row[2], score=round(row[3], 4)) for row in scored[:top_n]]


def token_hints(
    raw_name: str, products: list[dict], exclude: set[int], hint_n: int = HINT_N
) -> list[dict]:
    """Catalog rows sharing distinctive tokens with ``raw_name``.

    The difflib ratio in :func:`top_candidates` is whole-string, so a long
    retailer prefix ("Scarlet &amp; Violet: Paradox Rift booster") can push the
    genuinely correct row ("Paradox Rift Booster") out of the top 5. This is a
    second, token-based view so the operator can still reach it.
    """
    needle = expand_codes(tokenize(raw_name))
    if not needle:
        return []
    scored = []
    for p in products:
        if p["id"] in exclude:
            continue
        shared = needle & tokenize(p["name"])
        if not shared:
            continue
        # coverage of the raw_name's tokens, then catalog-name brevity, then rank
        coverage = len(shared) / len(needle)
        scored.append((-coverage, len(tokenize(p["name"])), p["rank"] or 10**9, p, coverage))
    scored.sort(key=lambda t: t[:3])
    return [dict(row[3], coverage=round(row[4], 2)) for row in scored[:hint_n]]


def render(
    raw_name: str, index: int, total: int, sites: str, products: list[dict], hint_n: int = HINT_N
) -> str:
    bar = "─" * 61
    lines = [bar, f"Calibration [{index}/{total}]: {raw_name}"]
    if sites:
        lines.append(f"Sites: {sites}")
    lines.append("")
    lines.append("Candidates:")
    shown = top_candidates(raw_name, products)
    for i, c in enumerate(shown, start=1):
        lines.append(
            f"  {i}. {c['name']} (ID: {c['id']})"
            f"  [{c['category']}, rank {c['rank']}, score {c['score']}]"
        )
    hints = token_hints(raw_name, products, {c["id"] for c in shown}, hint_n)
    if hints:
        lines.append("")
        lines.append("Also in catalog (token overlap, not part of the top-5):")
        for h in hints:
            lines.append(
                f"   - {h['name']} (ID: {h['id']})"
                f"  [{h['category']}, rank {h['rank']}, cov {h['coverage']}]"
            )
    lines.append(bar)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog", type=Path, help="curated catalog JSONL dump")
    ap.add_argument("raw_name", nargs="?", help="a single raw_name to score")
    ap.add_argument(
        "--file",
        type=Path,
        help="file of raw_names, one per line; 'raw_name\\tsites' also accepted",
    )
    ap.add_argument(
        "--hints",
        type=int,
        default=HINT_N,
        help=f"token-overlap rows to show below the top-5 (default {HINT_N}, 0 to disable)",
    )
    args = ap.parse_args()

    products = load_catalog(args.catalog)

    if args.file:
        entries = []
        for line in args.file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            name, _, sites = line.partition("\t")
            entries.append((name, sites))
    elif args.raw_name:
        entries = [(args.raw_name, "")]
    else:
        ap.error("pass a raw_name or --file")

    for i, (name, sites) in enumerate(entries, start=1):
        print(render(name, i, len(entries), sites, products, args.hints))
        print()


if __name__ == "__main__":
    main()
