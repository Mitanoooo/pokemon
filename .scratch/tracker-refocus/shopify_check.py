"""Ticket 18 check: does the availability block agree with Shopify's own `available`?

    venv/bin/python .scratch/tracker-refocus/shopify_check.py [site-substring ...]

For every cached page of a /collections/<handle> URL, fetches
/collections/<handle>/products.json and compares the block's reading per product
title against `any(variant.available)`. Prints the confusion counts plus the
first few disagreements, which is the only way to check an all-in-stock page:
the shop says which of its products are sold out even when the page shows none.
"""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402

PAGES = Path(__file__).parent / "pages"


def norm(name):
    return re.sub(r"\s+", " ", (name or "").replace("’", "'")).strip().casefold()


def main(argv):
    for path in sorted(Path("site_configs").glob("*.json")):
        config = json.loads(path.read_text())
        if config.get("disabled"):
            continue
        if argv and not any(a in path.stem for a in argv):
            continue
        urls = source_urls(config)
        if "/collections/" not in urls[0]:
            continue

        page = PAGES / f"{path.stem}-u1.html"
        if not page.exists():
            continue
        parsed = {norm(p["raw_name"]): p["availability"] for p in scrape_page(page.read_text(), config)}

        split = urlsplit(urls[0])
        handle = split.path.split("/collections/")[1].split("/")[0]
        api = f"{split.scheme}://{split.netloc}/collections/{handle}/products.json?limit=250"
        try:
            data = json.loads(fetch(api, config))
        except Exception as exc:
            print(f"{path.stem}: products.json failed — {exc}")
            continue
        time.sleep(1)

        truth = {}
        for product in data.get("products", []):
            available = any(v.get("available") for v in product.get("variants", []))
            truth[norm(product.get("title"))] = "in_stock" if available else "out_of_stock"

        pairs = Counter()
        disagreements = []
        for name, state in parsed.items():
            if name not in truth:
                pairs[(state, "(not in products.json)")] += 1
                continue
            pairs[(state, truth[name])] += 1
            if state != truth[name] and state != "preorder":
                disagreements.append((name, state, truth[name]))

        print(f"\n{path.stem}: {len(parsed)} parsed, {len(truth)} in products.json")
        for (mine, theirs), n in pairs.most_common():
            flag = "  <-- disagrees" if mine != theirs and mine != "preorder" else ""
            print(f"   {n:>4}  config={mine:<13} shopify={theirs}{flag}")
        for name, mine, theirs in disagreements[:5]:
            print(f"        {name[:60]!r} config={mine} shopify={theirs}")


if __name__ == "__main__":
    main(sys.argv[1:])
