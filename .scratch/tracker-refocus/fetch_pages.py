"""Cache page 1 of every non-disabled site so the availability pass can iterate offline.

    venv/bin/python .scratch/tracker-refocus/fetch_pages.py [site-substring ...]

Writes .scratch/tracker-refocus/pages/<config-stem>-u<N>.html, one file per
source URL (first MAX_URLS of them), and skips a file that already exists.
Ticket 18: writing an availability block means re-running the probe a dozen
times per site, and no shop should be fetched a dozen times for that.
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.fetcher import fetch  # noqa: E402
from scraper.paginator import source_urls  # noqa: E402

MAX_URLS = 3
OUT = Path(__file__).parent / "pages"


def main(patterns):
    OUT.mkdir(exist_ok=True)
    first = True
    for path in sorted(Path("site_configs").glob("*.json")):
        config = json.loads(path.read_text())
        if config.get("disabled"):
            continue
        stem = path.stem
        if patterns and not any(p in stem for p in patterns):
            continue
        for i, url in enumerate(source_urls(config)[:MAX_URLS], start=1):
            dest = OUT / f"{stem}-u{i}.html"
            if dest.exists():
                continue
            if not first:
                time.sleep(random.uniform(1, 4))
            first = False
            try:
                html = fetch(url, config)
            except Exception as exc:
                print(f"{stem} u{i}: {type(exc).__name__}: {exc}")
                continue
            dest.write_text(html)
            print(f"{stem} u{i}: {len(html)} bytes  {url}")


if __name__ == "__main__":
    main(sys.argv[1:])
