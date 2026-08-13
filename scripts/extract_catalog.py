#!/usr/bin/env python3
"""Convert the per-category catalog scrape dumps into catalog_scrape.json.

The ticket-07 browser scrape was run as 8 plain-text dumps (catalog_<category>.txt)
holding link labels and URLs, not the JSON the prompt asks for. The listing pages do
not expose the integer product id, so it is recovered here by joining each product's
URL slug against the local cardmarket_catalogue.json export.

Cardmarket derives a slug from the product name but drops some punctuation outright
("McDonald's" -> "McDonalds", "CSV9.5C" -> "CSV95C") while turning other runs into
hyphens. Folding both sides down to bare lowercase alphanumerics (see `fold`) makes
the slug and the catalogue name comparable, which resolves ~99% of products exactly.

Usage:
    python scripts/extract_catalog.py                     # writes catalog_scrape.json
    python scripts/extract_catalog.py -o other.json
"""

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_PAGE_HEADER = re.compile(r"^===\s*(?P<category>.+?)\s*\|\s*page\s*(?P<page>\d+)\s*===$")
_LINK = re.compile(r'^-\s*link\s+"(?P<label>.*)":\s*/url:\s*(?P<url>\S+)\s*$')


@dataclass(frozen=True)
class Entry:
    """One product line from a scrape dump, in the order it was listed."""

    slug: str
    label: str


@dataclass(frozen=True)
class Category:
    """A scraped category and the catalogue's `idCategory` for it.

    `id_category` is the value the ticket-07 scrape URLs filter on, which is also
    `cardmarket_products.id_category` on the server.
    """

    name: str
    id_category: int


@dataclass
class Stats:
    """Per-category resolution counts, reported in the summary."""

    matched: int = 0
    unresolved: int = 0
    duplicates: int = 0
    ambiguous: int = 0
    rescued: int = 0
    pages: int = 0
    unresolved_slugs: list[str] = field(default_factory=list)
    rescues: list[tuple[str, str]] = field(default_factory=list)


# Each scraped category and the dump file it was saved to.
SOURCES: list[tuple[Category, str]] = [
    (Category("Boosters", 52), "catalog_boosters.txt"),
    (Category("Booster Boxes", 53), "catalog_booster_boxes.txt"),
    (Category("Theme Decks", 54), "catalog_theme_decks.txt"),
    (Category("Trainer Kits", 1013), "catalog_trainer_kits.txt"),
    (Category("Tins", 1014), "catalog_tins.txt"),
    (Category("Box Sets", 1015), "catalog_box_sets.txt"),
    (Category("Elite Trainer Boxes", 1016), "catalog_elite_trainer_boxes.txt"),
    (Category("Blisters", 1083), "catalog_blisters.txt"),
]


def fold(text: str) -> str:
    """Reduce a slug or product name to a comparable key of bare alphanumerics."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", stripped.lower())


def parse_catalog_dump(text: str) -> tuple[list[Entry], int]:
    """Parse one catalog_<category>.txt dump into listing order plus a page count."""
    entries: list[Entry] = []
    pages = 0
    for line in text.splitlines():
        line = line.strip()
        header = _PAGE_HEADER.match(line)
        if header:
            pages = max(pages, int(header.group("page")))
            continue
        link = _LINK.match(line)
        if link:
            slug = link.group("url").rstrip("/").rsplit("/", 1)[-1]
            entries.append(Entry(slug=slug, label=link.group("label").strip()))
    return entries, pages


def clean_label(label: str) -> str:
    """Strip the expansion name that listing labels repeat ahead of the product name."""
    words = label.split()
    # Longest repeated opening phrase first, so a fully duplicated label halves cleanly.
    for size in range(len(words) // 2, 0, -1):
        head, rest = words[:size], words[size:]
        if rest[:size] == head:
            return " ".join(rest)
    return label


# Below this, a label suffix is too generic to trust: the catalogue really does contain
# rows named just "Booster", so a single trailing word would mis-attach an id.
_MIN_SUFFIX_WORDS = 2


def label_candidates(
    label: str,
    index: dict[tuple[int, str], list[dict]],
    id_category: int,
) -> list[dict]:
    """Resolve a product from its listing label when the slug is unusable.

    Labels arrive as expansion name + product name, so the catalogue name is a trailing
    run of words. Tries the longest suffix first and stops at the first hit.
    """
    words = label.split()
    for start in range(len(words) - _MIN_SUFFIX_WORDS + 1):
        candidates = index.get((id_category, fold(" ".join(words[start:]))))
        if candidates:
            return candidates
    return []


def build_index(products: list[dict]) -> dict[tuple[int, str], list[dict]]:
    """Index catalogue products by (idCategory, folded name), lowest idProduct first."""
    index: dict[tuple[int, str], list[dict]] = {}
    for product in products:
        key = (product["idCategory"], fold(product["name"]))
        index.setdefault(key, []).append(product)
    for candidates in index.values():
        candidates.sort(key=lambda p: p["idProduct"])
    return index


def resolve_category(
    entries: list[Entry],
    index: dict[tuple[int, str], list[dict]],
    category: Category,
) -> tuple[list[dict], Stats]:
    """Turn one category's listing order into catalog_scrape.json records.

    Repeats are dropped (consecutive scrape pages overlapped by a product), so ranks
    stay contiguous. Products absent from the catalogue export keep a null id rather
    than being discarded, matching the ticket-07 output contract.
    """
    records: list[dict] = []
    stats = Stats()
    seen: set[str] = set()

    for entry in entries:
        key = fold(entry.slug)
        if key in seen:
            stats.duplicates += 1
            continue
        seen.add(key)

        candidates = index.get((category.id_category, key), [])
        rescued = False
        if not candidates:
            # Some slugs omit a word ("Poke-Ball-Tin" for "Generic Poké Ball Tin") or are
            # outright broken ("LocExpansionName-..."), but the label still names the product.
            candidates = label_candidates(entry.label, index, category.id_category)
            rescued = bool(candidates)

        if candidates:
            stats.matched += 1
            if len(candidates) > 1:
                stats.ambiguous += 1
            product_id = candidates[0]["idProduct"]
            name = candidates[0]["name"]
            if rescued:
                stats.rescued += 1
                stats.rescues.append((entry.slug, name))
        else:
            stats.unresolved += 1
            stats.unresolved_slugs.append(entry.slug)
            product_id = None
            name = clean_label(entry.label)

        records.append({
            "cardmarket_product_id": product_id,
            "name": name,
            "category": category.name,
            "popularity_rank": len(records) + 1,
        })

    return records, stats


def header_categories(text: str) -> set[str]:
    """The category names a dump's own page headers claim."""
    return {
        m.group("category")
        for m in (_PAGE_HEADER.match(line.strip()) for line in text.splitlines())
        if m
    }


def extract(
    sources: list[tuple[Category, str]],
    products: list[dict],
) -> tuple[list[dict], dict[str, Stats]]:
    """Build the full catalog_scrape.json record list from the per-category dumps.

    `sources` pairs each category with the *text* of its dump (unlike `SOURCES`,
    which pairs it with a filename).
    """
    index = build_index(products)
    records: list[dict] = []
    stats_by_category: dict[str, Stats] = {}

    for category, text in sources:
        # Guard against a dump being mapped to the wrong idCategory, which would
        # silently curate the wrong products.
        claimed = header_categories(text)
        unexpected = claimed - {category.name}
        if unexpected:
            raise ValueError(
                f"{category.name} dump contains page headers for {sorted(unexpected)}"
            )

        entries, pages = parse_catalog_dump(text)
        category_records, stats = resolve_category(entries, index, category)
        stats.pages = pages
        records.extend(category_records)
        stats_by_category[category.name] = stats

    return records, stats_by_category


def load_catalogue(path: Path) -> list[dict]:
    """Read the products array out of the cardmarket_catalogue.json export."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["products"]


def _print_summary(stats_by_category: dict[str, Stats], total: int, nulls: int) -> None:
    width = max(len(name) for name in stats_by_category) + 1
    print("Scraped:")
    for name, stats in stats_by_category.items():
        print(
            f"  {name + ':':<{width}} {stats.matched + stats.unresolved:4d} products"
            f" ({stats.pages} pages, {stats.unresolved} unresolved,"
            f" {stats.duplicates} repeats dropped)"
        )
    print("  " + "─" * (width + 46))
    print(f"  {'Total:':<{width}} {total:4d} products")
    print(f"  Products with null cardmarket_product_id: {nulls}")

    ambiguous = sum(s.ambiguous for s in stats_by_category.values())
    if ambiguous:
        print(f"  Ambiguous names resolved to lowest product id: {ambiguous}")

    rescues = [r for s in stats_by_category.values() for r in s.rescues]
    if rescues:
        print(f"\nResolved via listing label, slug was unusable ({len(rescues)}) — check these:")
        for slug, name in rescues:
            print(f"  {slug}\n    -> {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-d", "--dumps-dir", type=Path, default=Path.cwd(),
        help="directory holding the catalog_<category>.txt dumps (default: cwd)",
    )
    parser.add_argument(
        "-c", "--catalogue", type=Path, default=Path("cardmarket_catalogue.json"),
        help="Cardmarket catalogue export to resolve product ids against",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("catalog_scrape.json"),
        help="where to write the ticket-07 format JSON (default: catalog_scrape.json)",
    )
    args = parser.parse_args()

    if not args.catalogue.exists():
        sys.exit(f"Catalogue not found: {args.catalogue}")

    sources = []
    for category, filename in SOURCES:
        path = args.dumps_dir / filename
        if not path.exists():
            sys.exit(f"Dump not found: {path}")
        sources.append((category, path.read_text(encoding="utf-8")))

    try:
        records, stats_by_category = extract(sources, load_catalogue(args.catalogue))
    except ValueError as exc:
        sys.exit(str(exc))

    nulls = sum(1 for r in records if r["cardmarket_product_id"] is None)
    args.output.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    _print_summary(stats_by_category, len(records), nulls)
    print(f"\nWrote {args.output} ({len(records)} entries, {len(records) - nulls} with ids)")

    unresolved = [
        (name, slug)
        for name, stats in stats_by_category.items()
        for slug in stats.unresolved_slugs
    ]
    if unresolved:
        print(f"\nUnresolved slugs ({len(unresolved)}) — absent from {args.catalogue.name},"
              " these get dropped by update_catalog.py:")
        for name, slug in unresolved:
            print(f"  {name:<20} {slug}")


if __name__ == "__main__":
    main()
