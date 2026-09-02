"""Ticket 18 helper: the state-bearing markup inside a site's product containers.

    venv/bin/python .scratch/tracker-refocus/badges.py <config.json> [--url URL] [--file PATH]
                                                        [--sel CSS] [--dump N]

The probe prints badge *text* by heuristic selector. This prints the tag name
and class list next to that text, which is what writing the block needs, plus
add-to-cart forms and buttons (the presence signal most Shopify themes have).
--url fetches and caches under pages/ so the same page can be re-read offline;
--dump N prints the raw HTML of container N to read an unfamiliar theme.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.parser import find_containers, scrape_page  # noqa: E402

from bs4 import BeautifulSoup  # noqa: E402

CANDIDATES = (
    '[class*="stock"]', '[class*="avail"]', '[class*="badge"]', '[class*="saatav"]',
    '[class*="ennakko"]', '[class*="sold"]', '[class*="loppu"]', '[class*="label"]',
    '[class*="tag"]', '[class*="status"]', 'button', 'form',
)

# Wordings that carry a state, matched against the whole container's text so an
# unclassed <p> (lelupartanen) shows up too.
WORDS = ("varastossa", "loppu", "saatavilla", "saatav", "ennakko", "tulossa", "saapuu",
         "julkaisu", "preorder", "pre-order", "pre order", "sold out", "in stock",
         "out of stock", "kommer", "släpp", "myymälä", "tilattavissa", "toimitusaika",
         "heti", "varasto")


def census(config, html, extra_sel=None, dump=None):
    soup = BeautifulSoup(html, "html.parser")
    containers = find_containers(soup, config)
    print(f"{len(containers)} container(s)")

    if dump is not None:
        print(containers[dump].prettify()[:6000])
        return

    seen = Counter()
    words = Counter()
    for el in containers:
        for selector in CANDIDATES + ((extra_sel,) if extra_sel else ()):
            for x in el.select(selector):
                classes = " ".join(x.get("class") or [])
                text = " ".join(x.get_text().split())[:60]
                extra = ""
                if x.name == "form":
                    extra = f" action={x.get('action')}"
                if x.name == "button":
                    extra = f" disabled={x.has_attr('disabled')} name={x.get('name')}"
                seen[(selector, x.name, classes, text + extra)] += 1
        text = " ".join(el.get_text().split()).lower()
        for word in WORDS:
            if word in text:
                match = re.search(r"[^.|]{0,30}" + re.escape(word) + r"[^.|]{0,30}", text)
                words[(word, match.group(0).strip() if match else word)] += 1

    print("\n-- elements (selector, tag, classes, text) --")
    for (selector, tag, classes, text), n in seen.most_common(60):
        print(f"{n:>5}x  {selector:<18} {tag:<8} .{classes[:44]:<44} {text}")

    print("\n-- state wordings in container text --")
    for (word, ctx), n in words.most_common(30):
        print(f"{n:>5}x  {word:<14} …{ctx}…")

    split = Counter(p["availability"] for p in scrape_page(html, config))
    print(f"\nsplit now: {dict(split)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--url")
    ap.add_argument("--file")
    ap.add_argument("--sel")
    ap.add_argument("--dump", type=int)
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text())
    if args.url:
        html = fetch(args.url, config)
        cache = Path(__file__).parent / "pages" / (
            re.sub(r"[^a-z0-9]+", "-", args.url.lower().split("://")[-1])[:80] + ".html")
        cache.write_text(html)
        print(f"cached {cache}")
    else:
        html = Path(args.file).read_text()
    census(config, html, extra_sel=args.sel, dump=args.dump)


if __name__ == "__main__":
    main()
