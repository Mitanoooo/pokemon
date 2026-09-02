"""Ticket 18 helper: every state-bearing text in the cached pages, per site.

    venv/bin/python .scratch/tracker-refocus/wordscan.py [site-substring ...]

Prints, per site, the smallest element that carries each state wording found
inside a product container: `count  tag.classes  "text"`. One compact table per
site is enough to write or check the availability block, and the preorder
wordings the ticket lists show up here or nowhere.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup  # noqa: E402

from scraper.parser import find_containers  # noqa: E402

PAGES = Path(__file__).parent / "pages"

WORDS = ("varastossa", "varastoss", "loppu", "saatav", "ennakko", "tulossa", "saapuu",
         "julkais", "preorder", "pre-order", "pre order", "sold out", "soldout",
         "in stock", "out of stock", "kommer", "släpp", "förköp", "myymälä",
         "tilattavissa", "toimitusaika", "heti", "ei varas", "tuotetta", "kpl",
         "unavailable", "available", "ennakkotilaus")

SKIP_TAGS = {"script", "style", "noscript"}


def leaf_texts(container):
    """(tag.classes, text) for the deepest element holding each state wording."""
    out = []
    for el in container.find_all(True):
        if el.name in SKIP_TAGS:
            continue
        if el.find(True, recursive=False) and el.find(string=True, recursive=False) is None:
            continue  # a pure wrapper: its children carry the text
        text = " ".join(el.get_text().split())
        low = text.lower()
        if not text or len(text) > 60:
            continue
        if not any(w in low for w in WORDS):
            continue
        label = el.name + "".join(f".{c}" for c in (el.get("class") or []))
        out.append((label, text))
    return out


def main(argv):
    for path in sorted(Path("site_configs").glob("*.json")):
        config = json.loads(path.read_text())
        if config.get("disabled"):
            continue
        if argv and not any(a in path.stem for a in argv):
            continue
        found: Counter = Counter()
        containers = 0
        for page in sorted(PAGES.glob(f"{path.stem}-u*.html")):
            soup = BeautifulSoup(page.read_text(), "html.parser")
            for container in find_containers(soup, config):
                containers += 1
                for row in set(leaf_texts(container)):
                    found[row] += 1
        block = config.get("availability") or {}
        print(f"\n=== {path.stem}  {containers} containers  "
              f"selector={block.get('selector') or (block.get('presence') or {}).get('selector') or '-'}")
        for (label, text), n in found.most_common(25):
            print(f"  {n:>4}x  {label[:58]:<58} {text[:60]!r}")
        if not found:
            print("  (no state wording inside any container)")


if __name__ == "__main__":
    main(sys.argv[1:])
