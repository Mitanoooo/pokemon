"""Ticket 17 audit helper: find and verify each shop's preorder category URL.

Discovery, per site: every link on the homepage and on the site's first source
URL whose href or anchor text reads preorder-ish, plus the same filter over the
site's sitemaps. Verification: fetch each candidate and count products with the
site's own config selectors, so a candidate that renders no listings is visible
as such.

    python .scratch/tracker-refocus/find_preorder_urls.py            # every site
    python .scratch/tracker-refocus/find_preorder_urls.py tcgkauppa  # one site

Writes .scratch/tracker-refocus/candidates.json. Operator tool, not shipped code.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import FetchError, fetch  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402

OUT = Path(__file__).parent / "candidates.json"

PREORDER_RE = re.compile(
    r"ennakko|ennakkotilau|tulossa|tulevat|pre-?order|pre_order|kommande|"
    r"kommer-snart|coming-soon|upcoming|julkaisu",
    re.I,
)
# Anchor text and hrefs both get matched; these words alone are too noisy in
# text ("tulossa pian" in a marketing banner) but fine paired with a link.
SKIP_HREF_RE = re.compile(r"\.(jpg|png|webp|pdf|css|js)$|^mailto:|^tel:", re.I)


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def links_from(html: str, base: str, site_host: str) -> "dict[str, str]":
    """Preorder-ish links on one page, as {absolute url: anchor text}."""
    found = {}
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        href = a.get("href", "")
        if not href or SKIP_HREF_RE.search(href):
            continue
        text = " ".join(a.get_text().split())[:60]
        if not (PREORDER_RE.search(href) or PREORDER_RE.search(text)):
            continue
        url = urljoin(base, href)
        if host_of(url) != site_host or urlparse(url).scheme not in ("http", "https"):
            continue
        found.setdefault(url.split("#")[0], text)
    return found


def sitemap_candidates(root: str, site_host: str) -> "dict[str, str]":
    """Preorder-ish URLs from the site's sitemap, one level of index following."""
    found = {}
    try:
        xml = fetch(urljoin(root, "/sitemap.xml"))
    except Exception:
        return found

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    children = [
        u for u in locs
        if u.endswith(".xml") and re.search(r"collection|categor|product|page", u, re.I)
    ][:4]
    for child in children:
        time.sleep(0.5)
        try:
            locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", fetch(child))
        except Exception:
            continue

    for url in locs:
        if url.endswith(".xml") or host_of(url) != site_host:
            continue
        if PREORDER_RE.search(url):
            found.setdefault(url.split("#")[0], "(sitemap)")
    return found


def verify(url: str, config: dict) -> dict:
    """Fetch a candidate and count what the site's config parses off it."""
    try:
        html = fetch(url, config)
    except (FetchError, NotImplementedError) as exc:
        return {"url": url, "error": str(exc)[:120]}
    try:
        products = scrape_page(html, config)
    except Exception as exc:
        return {"url": url, "error": f"parse failed: {exc}"[:120]}
    return {
        "url": url,
        "products": len(products),
        "samples": [p["raw_name"][:70] for p in products[:4]],
        "title": (BeautifulSoup(html, "html.parser").title.get_text(strip=True)[:80]
                  if BeautifulSoup(html, "html.parser").title else ""),
    }


def audit(path: Path) -> dict:
    config = json.loads(path.read_text())
    result = {
        "config": path.name,
        "site_name": config.get("site_name"),
        "disabled": bool(config.get("disabled")),
        "source_urls": source_urls(config),
        "candidates": [],
        "notes": [],
    }
    first = result["source_urls"][0]
    site_host = host_of(first)
    root = f"{urlparse(first).scheme}://{urlparse(first).hostname}"

    links: "dict[str, str]" = {}
    for page in (root + "/", first):
        try:
            html = fetch(page, config)
        except Exception as exc:
            result["notes"].append(f"{page}: {str(exc)[:100]}")
            continue
        links.update(links_from(html, page, site_host))
        time.sleep(1)

    links.update(sitemap_candidates(root, site_host))

    for url, text in sorted(links.items())[:14]:
        time.sleep(0.7)
        checked = verify(url, config)
        checked["link_text"] = text
        result["candidates"].append(checked)

    return result


def main() -> int:
    paths = sorted(Path("site_configs").glob("*.json"))
    if len(sys.argv) > 1:
        wanted = sys.argv[1:]
        paths = [p for p in paths if any(w in p.name for w in wanted)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(audit, paths))

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for r in results:
        hits = [c for c in r["candidates"] if c.get("products")]
        print(f"{r['config']:32} candidates={len(r['candidates'])} with_products={len(hits)}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
