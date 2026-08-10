"""
One-time script: fetches each site in pokemon_sivut_clean.txt, sends HTML to Claude,
and writes a selector config to site_configs/<domain>.json.

Run: python analyse_sites.py
Re-run a single site: python analyse_sites.py casagrande.fi
"""

import sys
import json
import time
import random
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import anthropic

SITES_FILE = Path("pokemon_sivut_clean.txt")
CONFIGS_DIR = Path("site_configs")
CONFIGS_DIR.mkdir(exist_ok=True)

HTML_TRUNCATE = 40_000  # chars sent to Claude
REQUEST_TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
}

SYSTEM_PROMPT = """You are a web scraping expert. You will be given the HTML of a Finnish
online retailer's product listing page that sells Pokémon sealed products (booster boxes,
Elite Trainer Boxes, booster bundles, collection boxes, etc.).

Your job is to identify CSS selectors and pagination so a Python scraper can extract
product listings from this page repeatedly.

Respond ONLY with a valid JSON object, no markdown, no explanation. Use this exact schema:

{
  "site_name": "Human-readable shop name",
  "method": "css" or "python",
  "selectors": {
    "product_container": "CSS selector for the element wrapping each product",
    "product_name": "CSS selector for product name (relative to container)",
    "price": "CSS selector for price (relative to container)",
    "in_stock": "CSS selector or null — element present means in stock, absent means out of stock",
    "product_url": "CSS selector for product link (relative to container), or null"
  },
  "pagination": {
    "type": "none" | "next_button" | "url_pattern",
    "selector": "CSS selector for next-page link, or null",
    "url_pattern": "URL pattern with {page} placeholder, or null",
    "max_pages": 5
  },
  "confidence": "high" | "medium" | "low",
  "notes": "Any caveats — JS rendering needed, unusual structure, etc."
}

If the page requires JavaScript rendering and you cannot identify products from static HTML,
set confidence to "low" and explain in notes.
If the structure is so complex that CSS selectors won't work, set method to "python" and
put a brief description in notes of what logic is needed instead."""

CLIENT = anthropic.Anthropic()


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lstrip("www.")


def config_path(url: str) -> Path:
    return CONFIGS_DIR / f"{domain_from_url(url)}.json"


def fetch_html(url: str) -> tuple[str | None, str | None]:
    """Returns (html, error). Tries requests first, no Playwright here."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text, None
    except Exception as e:
        return None, str(e)


def extract_body_text(html: str) -> str:
    """Strip scripts/styles, return cleaned HTML truncated for Claude."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "svg", "noscript"]):
        tag.decompose()
    cleaned = str(soup)
    return cleaned[:HTML_TRUNCATE]


def analyse_with_claude(url: str, html: str) -> dict:
    domain = domain_from_url(url)
    prompt = f"Site URL: {url}\nDomain: {domain}\n\nHTML:\n{html}"

    message = CLIENT.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if Claude adds them despite instructions
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "site_name": domain,
            "method": "css",
            "selectors": {},
            "pagination": {"type": "none"},
            "confidence": "low",
            "notes": f"Claude returned unparseable JSON: {raw[:200]}",
        }


def analyse_site(url: str, force: bool = False) -> None:
    path = config_path(url)
    domain = domain_from_url(url)

    if path.exists() and not force:
        print(f"  SKIP {domain} (config exists)")
        return

    print(f"  FETCH {url}")
    html, err = fetch_html(url)

    if err or not html:
        print(f"  ERROR {domain}: {err}")
        config = {
            "site_name": domain,
            "method": "css",
            "selectors": {},
            "pagination": {"type": "none"},
            "confidence": "low",
            "notes": f"Fetch failed: {err}",
        }
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        return

    body = extract_body_text(html)
    print(f"  ANALYSE {domain} ({len(body)} chars → Claude)")

    config = analyse_with_claude(url, body)
    config["source_url"] = url
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

    conf = config.get("confidence", "?")
    print(f"  DONE {domain} — confidence: {conf}")


def main() -> None:
    urls = [u.strip() for u in SITES_FILE.read_text().splitlines() if u.strip()]

    # If a domain is passed as argument, only reanalyse that one
    if len(sys.argv) > 1:
        target = sys.argv[1].lstrip("www.")
        urls = [u for u in urls if target in u]
        if not urls:
            print(f"No URL found matching '{sys.argv[1]}'")
            sys.exit(1)
        force = True
    else:
        force = False

    print(f"Analysing {len(urls)} site(s)...\n")

    for i, url in enumerate(urls):
        analyse_site(url, force=force)
        if i < len(urls) - 1:
            delay = random.uniform(2, 5)
            time.sleep(delay)

    print("\nDone. Configs written to site_configs/")
    print("Review low-confidence sites:")
    for p in sorted(CONFIGS_DIR.glob("*.json")):
        cfg = json.loads(p.read_text())
        if cfg.get("confidence") == "low":
            print(f"  {p.name}: {cfg.get('notes', '')[:80]}")


if __name__ == "__main__":
    main()
