"""Ticket 17 audit helper, pass 2: ask each platform for its category list.

Pass 1 (find_preorder_urls.py) crawled links and sitemaps, which misses a
preorder category that is not linked from the front page. This pass asks the
shop software instead:

- Shopify: /collections.json lists every collection with its handle and title.
- WooCommerce: the product_cat sitemap and the Store API category endpoint.
- everything else: a list of guessed paths per URL shape.

Candidates matching the preorder wordings are then fetched and parsed with the
site's own config, same as pass 1. Writes candidates2.json.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402

from find_preorder_urls import PREORDER_RE, host_of, verify  # noqa: E402

OUT = Path(__file__).parent / "candidates2.json"

SHOPIFY_GUESSES = (
    "/collections/ennakkotilaukset", "/collections/ennakkotilaus",
    "/collections/ennakko", "/collections/ennakkomyynti", "/collections/tulossa",
    "/collections/pre-order", "/collections/pre-orders", "/collections/preorder",
    "/collections/preorders", "/collections/kommande", "/collections/kommer-snart",
)
WOO_GUESSES = (
    "/product-category/ennakkotilaukset/", "/product-category/ennakkotilaus/",
    "/product-category/ennakko/", "/product-category/pre-order/",
    "/ennakkotilaukset/", "/ennakkotilaus/", "/tuoteryhma/ennakkotilaukset/",
    "/kategoria/ennakkotilaukset/", "/tuotetyyppi/ennakkotilaus/",
)
PLAIN_GUESSES = (
    "/ennakkotilaukset", "/ennakkotilaus", "/ennakot", "/ennakkotuotteet",
    "/tulossa", "/pre-order", "/preorder",
)


def _root(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.hostname}"


def shopify_collections(root: str) -> "dict[str, str]":
    """Every collection whose handle or title reads preorder-ish."""
    found = {}
    for page in (1, 2):
        try:
            data = json.loads(fetch(f"{root}/collections.json?limit=250&page={page}"))
        except Exception:
            break
        collections = data.get("collections") or []
        for coll in collections:
            handle = coll.get("handle", "")
            title = coll.get("title", "")
            if PREORDER_RE.search(handle) or PREORDER_RE.search(title):
                found[f"{root}/collections/{handle}"] = f"collections.json: {title[:40]}"
        if len(collections) < 250:
            break
        time.sleep(0.5)
    return found


WOO_TAXONOMY_PATHS = (
    "/product_cat-sitemap.xml",
    "/product-category-sitemap.xml",
    "/wp-sitemap-taxonomies-product_cat-1.xml",
    "/wp-json/wc/store/v1/products/categories?per_page=100",
    "/wp-json/wc/store/products/categories?per_page=100",
)


def woo_categories(root: str, site_host: str) -> "dict[str, str]":
    found = {}
    for path in WOO_TAXONOMY_PATHS:
        try:
            body = fetch(root + path)
        except Exception:
            continue
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        urls += re.findall(r'"permalink"\s*:\s*"([^"]+)"', body)
        for url in urls:
            url = url.replace("\\/", "/")
            if host_of(url) == site_host and PREORDER_RE.search(url):
                found.setdefault(url, f"woo {path}")
        time.sleep(0.4)
    return found


def guesses_for(first_url: str) -> "tuple[str, ...]":
    if "/collections/" in first_url:
        return SHOPIFY_GUESSES
    if re.search(r"/product-category/|/tuote/|/product/|\?s=", first_url):
        return WOO_GUESSES + PLAIN_GUESSES
    return PLAIN_GUESSES + WOO_GUESSES


def audit(path: Path) -> dict:
    config = json.loads(path.read_text())
    first = source_urls(config)[0]
    root = _root(first)
    site_host = host_of(first)

    result = {"config": path.name, "site_name": config.get("site_name"),
              "disabled": bool(config.get("disabled")), "candidates": []}

    links: "dict[str, str]" = {}
    if "/collections/" in first:
        links.update(shopify_collections(root))
    links.update(woo_categories(root, site_host))
    for guess in guesses_for(first):
        links.setdefault(root + guess, "(guess)")

    for url, text in sorted(links.items(), key=lambda kv: kv[1] == "(guess)")[:24]:
        time.sleep(0.5)
        checked = verify(url, config)
        checked["link_text"] = text
        if checked.get("products") or not checked.get("error"):
            result["candidates"].append(checked)

    return result


def main() -> int:
    paths = sorted(Path("site_configs").glob("*.json"))
    if len(sys.argv) > 1:
        paths = [p for p in paths if any(w in p.name for w in sys.argv[1:])]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(audit, paths))

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for r in results:
        hits = [c for c in r["candidates"] if c.get("products")]
        print(f"{r['config']:32} reachable={len(r['candidates'])} with_products={len(hits)}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
