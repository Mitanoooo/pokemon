"""Ticket 17 audit, pass 5: control checks plus the normal-category scan.

Three jobs:

1. `--control`: several shops returned the same product count for every guessed
   path (swagykarp 8 for four spellings, tcgkauppa 27 for five). Either the shop
   resolves them all to one real category, or it serves a soft-404 listing for
   anything. A nonsense path settles it: same count means the "preorder page" is
   not real.
2. `--extra`: the slugs passes 3 and 4 got wrong or could not reach.
3. `--scan` (default): page 1 of every site's normal source URLs, with the
   availability split its own config produces. That answers the second half of
   the ticket, whether a shop without a preorder page still shows preorders in
   its normal categories, and whether the badge is readable.
"""
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402

NAME_RE = re.compile(r"ennakko|julkaisu|tulossa|pre-?order|kommande|coming soon", re.I)

CONTROL = {
    "swagykarp.fi.json": [
        "https://swagykarp.fi/ennakkotilaukset/",
        "https://swagykarp.fi/zzz-ei-ole-olemassa/",
    ],
    "tcgkauppa.fi.json": [
        "https://www.tcgkauppa.fi/ennakkotilaukset/",
        "https://www.tcgkauppa.fi/zzz-ei-ole-olemassa/",
    ],
    "pokepulls.fi.json": [
        "https://pokepulls.fi/kategoria/ennakkotilattavissa",
        "https://pokepulls.fi/kategoria/zzz-ei-ole-olemassa",
    ],
    "proshop.fi.json": [
        "https://www.proshop.fi/ennakot",
        "https://www.proshop.fi/zzz-ei-ole-olemassa",
    ],
}

EXTRA = {
    "korttistoppi.fi.json": [
        "https://www.korttistoppi.fi/tuoteryhma/ennakkotilaus",
        "https://www.korttistoppi.fi/tuoteryhma/ennakkotilaus/page/2",
    ],
    "euroelite.fi.json": [
        "https://www.euroelite.fi/ennakkotilaus/",
        "https://www.euroelite.fi/ennakkotilaus",
    ],
    "kevinshobbyshop.com.json": [
        "https://kevinshobbyshop.com/shop/?yith_wcan=1&filter_game=pokemon&query_type_game=or&filter_availability=pre-order",
        "https://kevinshobbyshop.com/shop/page/2/?yith_wcan=1&filter_game=pokemon&query_type_game=or&filter_availability=pre-order",
    ],
    "pelienmaa.com.json": [
        "https://pelienmaa.com/collections/pre-order?filter.p.product_type=Pok%C3%A9mon",
    ],
    "spelparken.se.json": [
        "https://spelparken.se/collections/forkop",
    ],
}


def check(config: dict, url: str) -> str:
    try:
        html = fetch(url, config)
    except Exception as exc:
        return f"ERROR {str(exc)[:100]}"
    products = scrape_page(html, config)
    split = dict(Counter(p["availability"] for p in products))
    names = [p["raw_name"][:52] for p in products[:3]]
    preorder_names = sum(1 for p in products if NAME_RE.search(p["raw_name"]))
    return (f"{len(products):>3} products  {split}  preorder-ish names={preorder_names}"
            f"  bytes={len(html)}\n            {names}")


def run_group(group: dict) -> int:
    for filename, urls in group.items():
        config = json.loads((Path("site_configs") / filename).read_text())
        print(f"== {filename}")
        for i, url in enumerate(urls):
            if i:
                time.sleep(2)
            print(f"    {url[:100]}\n        {check(config, url)}")
    return 0


def scan(path: Path) -> dict:
    config = json.loads(path.read_text())
    urls = source_urls(config)
    out = {
        "config": path.name,
        "site_name": config.get("site_name"),
        "disabled": bool(config.get("disabled")),
        "availability_mode": (config.get("availability") or {}).get("mode"),
        "has_availability_block": bool(config.get("availability")),
        "normal_urls": len(urls),
        "listings": 0,
        "availability": {},
        "preorder_names": 0,
        "examples": [],
        "errors": [],
    }
    split: Counter = Counter()
    for i, url in enumerate(urls[:3]):
        if i:
            time.sleep(1.5)
        try:
            html = fetch(url, config)
        except Exception as exc:
            out["errors"].append(f"{url[:70]}: {str(exc)[:70]}")
            continue
        for p in scrape_page(html, config):
            out["listings"] += 1
            split[p["availability"]] += 1
            if NAME_RE.search(p["raw_name"]):
                out["preorder_names"] += 1
                if len(out["examples"]) < 3:
                    out["examples"].append(
                        f"{p['raw_name'][:60]} [{p['availability']}/{p['availability_text']}]")
    out["availability"] = dict(split)
    return out


def main() -> int:
    if "--control" in sys.argv:
        return run_group(CONTROL)
    if "--extra" in sys.argv:
        return run_group(EXTRA)

    paths = sorted(Path("site_configs").glob("*.json"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(scan, paths))
    Path(".scratch/tracker-refocus/normal_scan.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False))
    for r in results:
        print(f"{r['config']:28} urls={r['normal_urls']:>2} listings={r['listings']:>4} "
              f"preorder_names={r['preorder_names']:>3} mode={str(r['availability_mode']):>6} "
              f"{r['availability']} {'DISABLED' if r['disabled'] else ''}")
        for ex in r["examples"]:
            print(f"      {ex}")
        for err in r["errors"]:
            print(f"      ERR {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
