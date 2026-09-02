"""Ticket 17 audit, pass 4: settle the ambiguous cases from pass 3.

Three questions pass 3 left open:

- Is a collection that parsed 0 products empty, or are the selectors wrong?
  Shopify answers that directly: /collections/<handle>/products.json.
- Does a query parameter actually filter, or does the shop ignore it? Compare
  the product count with and without it.
- Retries for the shops that rate-limited or timed out.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402

SHOPIFY_JSON = [
    "https://pbcards.fi/collections/pokemon-pre-orders/products.json?limit=250",
    "https://pbcards.fi/collections/pre-orders/products.json?limit=250",
    "https://www.ellimadelli.fi/collections/ennakkotilaus-tuotteet/products.json?limit=250",
    "https://godofcards.com/en-fi/collections/pre-order/products.json?limit=250",
    "https://peliparatiisi.net/collections/pokemon-tcg-ennakkotilaukset/products.json?limit=250",
    "https://blockhousegames.net/collections/ennakkotilaukset/products.json?limit=250",
    "https://pelikrypta.fi/collections/tuoteryhma-ennakkotilaukset/products.json?limit=250",
]

# (config, url with the filter, url without) — same page, one difference.
PAIRS = [
    ("prisma.fi.json",
     "https://www.prisma.fi/tuotemerkit/pokemon-tcg?ennakkotilaus=1",
     "https://www.prisma.fi/tuotemerkit/pokemon-tcg"),
    ("karkkainen.com.json",
     "https://www.karkkainen.com/verkkokauppa/kerailykortit?availability=PreOrder",
     "https://www.karkkainen.com/verkkokauppa/kerailykortit"),
    ("maxgaming.fi.json",
     "https://www.maxgaming.fi/fi/pokemon?instock=0",
     "https://www.maxgaming.fi/fi/pokemon"),
    ("proshop.fi.json",
     "https://www.proshop.fi/Pokemon?f~pokmon_type=kort-og-tilbehor&pre=1",
     "https://www.proshop.fi/Pokemon?f~pokmon_type=kort-og-tilbehor&pre=0"),
    ("blockhousegames.net.json",
     "https://blockhousegames.net/collections/ennakkotilaukset/pokemon",
     "https://blockhousegames.net/collections/ennakkotilaukset"),
]

RETRIES = [
    ("pokepulls.fi.json", "https://pokepulls.fi/kategoria/ennakkotilattavissa"),
    ("kerailykortti.fi.json", "https://www.xn--kerilykortti-icb.fi/ennakkotilaukset/"),
    ("kerailykortti.fi.json", "https://www.xn--kerilykortti-icb.fi/tuotetyyppi/ennakkotilaus/"),
]

# Which Pokémon collections does Pelikrypta have now? Its configured one 404s.
COLLECTION_LISTS = [
    ("pelikrypta.fi", "https://pelikrypta.fi/collections.json?limit=250", r"pokemon|pokémon"),
]


def count_products(url: str) -> str:
    try:
        data = json.loads(fetch(url))
    except Exception as exc:
        return f"ERROR {str(exc)[:90]}"
    products = data.get("products") or []
    titles = [p.get("title", "")[:50] for p in products[:4]]
    return f"{len(products)} products in JSON  {titles}"


def parse_count(config: dict, url: str) -> str:
    try:
        html = fetch(url, config)
    except Exception as exc:
        return f"ERROR {str(exc)[:90]}"
    products = scrape_page(html, config)
    return f"{len(products)} parsed  first={[p['raw_name'][:40] for p in products[:2]]}"


def main() -> int:
    print("── Shopify products.json (is the collection empty?) ──")
    for url in SHOPIFY_JSON:
        print(f"  {url[:88]}\n      {count_products(url)}")
        time.sleep(1)

    print("\n── does the filter parameter change anything? ──")
    for filename, filtered, plain in PAIRS:
        config = json.loads((Path("site_configs") / filename).read_text())
        print(f"  {filename}")
        print(f"      filtered: {parse_count(config, filtered)}")
        time.sleep(2)
        print(f"      plain:    {parse_count(config, plain)}")
        time.sleep(2)

    print("\n── retries ──")
    for filename, url in RETRIES:
        config = json.loads((Path("site_configs") / filename).read_text())
        print(f"  {url[:88]}\n      {parse_count(config, url)}")
        time.sleep(2)

    print("\n── collection lists ──")
    for label, url, pattern in COLLECTION_LISTS:
        try:
            data = json.loads(fetch(url))
        except Exception as exc:
            print(f"  {label}: ERROR {exc}")
            continue
        matches = [
            (c.get("handle"), c.get("title"))
            for c in data.get("collections", [])
            if re.search(pattern, f"{c.get('handle')} {c.get('title')}", re.I)
        ]
        print(f"  {label}: {len(matches)} matching collection(s)")
        for handle, title in matches[:20]:
            print(f"      {handle}  —  {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
