"""Ticket 17 audit, pass 3: targeted per-site checks plus a preorder name scan.

Two jobs:

1. `CHECKS` — the hand-picked URLs passes 1 and 2 pointed at: a `pre=1` filter,
   a Shopify tag-filtered collection, a locale variant, a renamed collection.
2. `--names` — page 1 of every site's normal source URLs, counting listing names
   that read preorder-ish. That answers the other half of the ticket: whether a
   shop with no preorder page still shows its preorders in a normal category.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402

NAME_RE = re.compile(r"ennakko|julkaisu|tulossa|pre-?order|kommande|coming soon", re.I)

CHECKS = {
    "proshop.fi.json": [
        "https://www.proshop.fi/Pokemon?f~pokmon_type=kort-og-tilbehor&pre=1",
        "https://www.proshop.fi/Pokemon?pre=1",
    ],
    "godofcards.com.json": [
        "https://godofcards.com/en-fi/collections/pre-order",
        "https://godofcards.com/en-fi/collections/pre-order?filter.p.product_type=Pokemon",
        "https://godofcards.com/en-fi/collections/english-pokemon-cards?filter.v.availability=0",
    ],
    "pbcards.fi.json": [
        "https://pbcards.fi/collections/pokemon-pre-orders",
        "https://pbcards.fi/collections/pre-orders",
    ],
    "ellimadelli.fi.json": [
        "https://www.ellimadelli.fi/collections/ennakkotilaus-tuotteet",
        "https://www.ellimadelli.fi/collections/ennakkotilaus-tuotteet?page=1",
    ],
    "peliparatiisi.net.json": [
        "https://peliparatiisi.net/en/collections/pokemon-tcg-ennakkotilaukset",
        "https://peliparatiisi.net/en/collections/pokemon-tcg-ennakkotilaukset?page=2",
    ],
    "pelikrypta.fi.json": [
        "https://pelikrypta.fi/collections/pokemon-trading-card-game",
        "https://pelikrypta.fi/collections/tuoteryhma-ennakkotilaukset",
        "https://pelikrypta.fi/collections/tuoteryhma-ennakkotilaukset/pokemon",
    ],
    "blockhousegames.net.json": [
        "https://blockhousegames.net/collections/ennakkotilaukset/pokemon",
        "https://blockhousegames.net/collections/ennakkotilaukset/pokemon-tcg",
        "https://blockhousegames.net/collections/ennakkotilaukset?filter.p.product_type=Pok%C3%A9mon",
    ],
    "tcgkauppa.fi.json": [
        "https://www.tcgkauppa.fi/ennakkotilaukset/",
        "https://www.tcgkauppa.fi/ennakkotilaukset/page/2/",
        "https://www.tcgkauppa.fi/ennakkotilaukset/?tuote-osasto=pokemon",
        "https://www.tcgkauppa.fi/tuote-osasto/pokemon/?product_cat=ennakkotilaukset",
    ],
    "swagykarp.fi.json": [
        "https://swagykarp.fi/ennakkotilaukset/",
        "https://swagykarp.fi/ennakkotilaukset/page/2/",
    ],
    "pokepulls.fi.json": [
        "https://pokepulls.fi/kategoria/ennakkotilattavissa",
        "https://pokepulls.fi/kategoria/ennakkotilattavissa/page/2/",
    ],
    "karkkainen.com.json": [
        "https://www.karkkainen.com/verkkokauppa/ennakkotilaukset",
        "https://www.karkkainen.com/verkkokauppa/kerailykortit?availability=PreOrder",
    ],
    "karukortti.fi.json": [
        "https://karukortti.fi/kategoria/ennakkotilaukset",
        "https://karukortti.fi/category/ennakkotilaukset",
        "https://karukortti.fi/kategoria/ennakko",
    ],
    "kerailykortti.fi.json": [
        "https://www.xn--kerilykortti-icb.fi/ennakkotilaukset/",
        "https://www.xn--kerilykortti-icb.fi/ennakko/",
        "https://www.xn--kerilykortti-icb.fi/tuotetyyppi/ennakkotilaus/",
    ],
    "muovitukku.fi.json": [
        "https://www.muovitukku.fi/tuote-osasto/ennakkotilaukset/",
        "https://www.muovitukku.fi/ennakkotilaukset/",
    ],
    "muksumassi.fi.json": [
        "https://muksumassi.fi/ennakkotilaukset/",
        "https://muksumassi.fi/uutuudet/",
    ],
    "pelimies.fi.json": [
        "https://pelimies.fi/tulevat-tuotteet-v2/",
        "https://pelimies.fi/tuote-osasto/ennakkotilaukset/",
    ],
    "poromagia.com.json": [
        "https://poromagia.com/fi/catalogue/category/pokemon/",
        "https://poromagia.com/fi/catalogue/category/ennakkotilaukset/",
        "https://poromagia.com/fi/catalogue/?q=ennakko",
    ],
    "prisma.fi.json": [
        "https://www.prisma.fi/tuotemerkit/pokemon-tcg?ennakkotilaus=1",
        "https://www.prisma.fi/ennakkotilaukset",
    ],
    "maxgaming.fi.json": [
        "https://www.maxgaming.fi/fi/ennakkotilaukset",
        "https://www.maxgaming.fi/fi/pokemon?instock=0",
        "https://www.maxgaming.fi/fi/kommande",
    ],
    "kodintavaratalo.fi.json": [
        "https://kodintavaratalo.fi/ennakkotilaukset",
        "https://kodintavaratalo.fi/tulossa",
    ],
    "fantasialinna.com.json": [
        "https://www.fantasialinna.com/verkkokauppa/ennakkotilaukset",
        "https://www.fantasialinna.com/verkkokauppa/ennakot",
    ],
    "casagrande.fi.json": [
        "https://casagrande.fi/collections/ennakkotilaukset",
        "https://casagrande.fi/collections/pre-order",
    ],
    "lelupartanen.fi.json": [
        "https://lelupartanen.fi/category/ennakkotilaukset",
        "https://lelupartanen.fi/ennakkotilaukset",
    ],
    "kevinshobbyshop.com.json": [
        "https://kevinshobbyshop.com/product-category/pre-orders/",
        "https://kevinshobbyshop.com/shop/?yith_wcan=1&filter_game=pokemon&query_type_game=or&filter_availability=pre-order",
    ],
    "korttistoppi.fi.json": [
        "https://www.korttistoppi.fi/tuoteryhma/ennakkotilaukset",
        "https://www.korttistoppi.fi/tuoteryhma/tulossa",
    ],
    "muovijalelu.fi.json": [
        "https://www.muovijalelu.fi/product-category/ennakkotilaukset/",
        "https://www.muovijalelu.fi/?s=ennakkotilaus&post_type=product",
    ],
    "flea.fi.json": [
        "https://www.flea.fi/collections/ennakkotilaukset",
        "https://www.flea.fi/collections/pokemon?filter.v.availability=0",
    ],
    "spelparken.se.json": [
        "https://spelparken.se/collections/kommande",
        "https://spelparken.se/collections/pre-order",
    ],
    "vpd.fi.json": [
        "https://www.vpd.fi/pokemon-kortit/boosterit.html?ennakkotilaustuote=1",
        "https://www.vpd.fi/pokemon-kortit/displayt.html?ennakkotilaustuote=1",
    ],
}


def check_one(item) -> dict:
    filename, urls = item
    config = json.loads((Path("site_configs") / filename).read_text())
    out = {"config": filename, "results": []}
    for i, url in enumerate(urls):
        if i:
            time.sleep(1)
        row = {"url": url}
        try:
            html = fetch(url, config)
        except Exception as exc:
            row["error"] = str(exc)[:110]
            out["results"].append(row)
            continue
        products = scrape_page(html, config)
        row["products"] = len(products)
        row["samples"] = [p["raw_name"][:60] for p in products[:5]]
        row["preorder_names"] = sum(1 for p in products if NAME_RE.search(p["raw_name"]))
        row["bytes"] = len(html)
        out["results"].append(row)
    return out


def scan_names(path: Path) -> dict:
    """Page 1 of each normal source URL: how many names read preorder-ish."""
    config = json.loads(path.read_text())
    out = {"config": path.name, "disabled": bool(config.get("disabled")),
           "listings": 0, "preorder_names": 0, "examples": [], "errors": []}
    for i, url in enumerate(source_urls(config)[:4]):
        if i:
            time.sleep(1)
        try:
            html = fetch(url, config)
        except Exception as exc:
            out["errors"].append(f"{url}: {str(exc)[:80]}")
            continue
        for p in scrape_page(html, config):
            out["listings"] += 1
            if NAME_RE.search(p["raw_name"]):
                out["preorder_names"] += 1
                if len(out["examples"]) < 4:
                    out["examples"].append(p["raw_name"][:70])
    return out


def main() -> int:
    if "--names" in sys.argv:
        paths = sorted(Path("site_configs").glob("*.json"))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(scan_names, paths))
        Path(".scratch/tracker-refocus/name_scan.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False))
        for r in results:
            print(f"{r['config']:32} listings={r['listings']:>4} "
                  f"preorder_names={r['preorder_names']:>3} "
                  f"{'DISABLED' if r['disabled'] else ''} {r['errors'] or ''}")
        return 0

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check_one, CHECKS.items()))
    Path(".scratch/tracker-refocus/pass3.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False))
    for r in results:
        print("==", r["config"])
        for row in r["results"]:
            if "error" in row:
                print(f"    ERR  {row['url'][:95]}  {row['error'][:60]}")
            else:
                print(f"    {row['products']:>4} ({row['preorder_names']} preorder-ish names)"
                      f"  {row['url'][:90]}")
                if row["products"]:
                    print(f"          {row['samples'][:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
