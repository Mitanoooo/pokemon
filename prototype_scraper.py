# PROTOTYPE — answers: do the site_configs selectors actually extract products?
# Run: venv/bin/python prototype_scraper.py
# Delete after validated.

import json
import time
import random
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

CONFIGS_DIR = Path("site_configs")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
}


def fetch(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    FETCH ERROR: {e}")
        return None


def parse_price(text: str) -> str:
    return " ".join(text.split()).strip()


def scrape_page(html: str, cfg: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    sel = cfg["selectors"]
    results = []

    if not sel.get("product_container"):
        return []  # config incomplete (blocked/low-confidence site)

    containers = soup.select(sel["product_container"])
    if not containers:
        return []

    for c in containers:
        # Name
        name_el = c.select_one(sel["product_name"]) if sel.get("product_name") else None
        name = name_el.get_text(strip=True) if name_el else "?"

        # Price
        price_el = c.select_one(sel["price"]) if sel.get("price") else None
        price = parse_price(price_el.get_text()) if price_el else "?"

        # Stock — handle both normal and inverted selectors per config notes
        in_stock_sel = sel.get("in_stock")
        notes = cfg.get("notes", "").lower()
        if in_stock_sel:
            stock_el = c.select_one(in_stock_sel)
            if "inverted" in notes or "out of stock" in notes and "absence" in notes:
                # inverted: presence of selector = OUT of stock
                in_stock = stock_el is None
            elif "instock" in in_stock_sel or "instock" in (cfg.get("notes") or ""):
                # WooCommerce: check container's own class list
                in_stock = "instock" in c.get("class", [])
            else:
                in_stock = stock_el is not None
        else:
            in_stock = None  # unknown

        # URL
        url_sel = sel.get("product_url")
        url_el = c.select_one(url_sel) if url_sel else None
        product_url = url_el.get("href", "") if url_el else ""

        results.append({
            "name": name,
            "price": price,
            "in_stock": in_stock,
            "url": product_url,
        })

    return results


def scrape_site(cfg: dict) -> list[dict]:
    pagination = cfg.get("pagination", {})
    ptype = pagination.get("type", "none")
    base_url = cfg["source_url"]
    all_products = []

    if ptype == "none":
        pages = [base_url]
    elif ptype == "url_pattern":
        pattern = pagination.get("url_pattern", "")
        max_p = pagination.get("max_pages", 3)
        # Resolve relative patterns against base_url
        from urllib.parse import urljoin
        def resolve(p, n):
            url = p.replace("{page}", str(n)).replace("{offset}", str(n))
            return url if url.startswith("http") else urljoin(base_url, url)
        pages = [base_url] + [resolve(pattern, p) for p in range(2, max_p + 1)]
    elif ptype == "next_button":
        pages = [base_url]  # prototype: only first page for next_button sites
    else:
        pages = [base_url]

    for i, url in enumerate(pages):
        if i > 0:
            time.sleep(random.uniform(1.5, 3))
        print(f"    page {i+1}: {url}")
        html = fetch(url)
        if not html:
            break
        products = scrape_page(html, cfg)
        if not products:
            print(f"    WARNING: 0 products on page {i+1} — stopping pagination")
            break
        all_products.extend(products)
        print(f"    found {len(products)} products (total: {len(all_products)})")

    return all_products


def main():
    import sys
    filter_names = set(sys.argv[1:])  # optional: pass domain names to test only those

    all_configs = sorted(CONFIGS_DIR.glob("*.json"))
    configs = [
        c for c in all_configs
        if not filter_names or any(f in c.stem for f in filter_names)
    ]
    print(f"Testing {len(configs)} site config(s)\n{'='*60}\n")

    for config_path in configs:
        cfg = json.loads(config_path.read_text())
        site = cfg["site_name"]
        confidence = cfg.get("confidence", "?")
        print(f"SITE: {site}  (confidence: {confidence})")

        products = scrape_site(cfg)

        print(f"\n  RESULT: {len(products)} products extracted")
        if products:
            print("  First 3 products:")
            for p in products[:3]:
                stock = "in stock" if p["in_stock"] else ("out of stock" if p["in_stock"] is False else "unknown")
                print(f"    - {p['name'][:60]:<60} {p['price']:<12} {stock}")
        else:
            print("  !! NO PRODUCTS — selector likely broken or JS-rendered")

        print()
        time.sleep(random.uniform(2, 4))

    print("="*60)
    print("Prototype complete. Check results above.")
    print("For sites with 0 products: inspect HTML manually or flag for Playwright.")


if __name__ == "__main__":
    main()
