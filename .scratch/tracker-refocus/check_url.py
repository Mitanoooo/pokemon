"""Ticket 17 audit helper: parse one URL with one site's config.

    python .scratch/tracker-refocus/check_url.py site_configs/tcgkauppa.fi.json URL [URL...]

Prints the product count, the first few names, and the availability split, which
is what the audit records per candidate URL.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.parser import scrape_page  # noqa: E402


def main() -> int:
    config = json.loads(Path(sys.argv[1]).read_text())
    for i, url in enumerate(sys.argv[2:]):
        if i:
            time.sleep(1)
        try:
            html = fetch(url, config)
        except Exception as exc:
            print(f"{url}\n    ERROR {exc}")
            continue
        products = scrape_page(html, config)
        split = Counter(p["availability"] for p in products)
        print(f"{url}\n    {len(products)} products  {dict(split)}  bytes={len(html)}")
        for p in products[:6]:
            print(f"      {p['raw_name'][:74]!r} {p['price']} {p['availability']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
