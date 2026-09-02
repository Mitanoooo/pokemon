"""Ticket 18 helper: the probe's census over the cached pages, no network.

    venv/bin/python .scratch/tracker-refocus/split.py [site-substring ...] [--full]

Default prints one --all-style line per site over every pages/<stem>-u*.html
that fetch_pages.py cached, so a config edit can be checked against all 29 live
sites in a second. --full prints the single-site report instead.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.probe import Census, format_all_line, format_report  # noqa: E402

PAGES = Path(__file__).parent / "pages"


def main(argv):
    full = "--full" in argv
    patterns = [a for a in argv if not a.startswith("--")]

    for path in sorted(Path("site_configs").glob("*.json")):
        config = json.loads(path.read_text())
        if config.get("disabled"):
            continue
        if patterns and not any(p in path.stem for p in patterns):
            continue
        pages = sorted(PAGES.glob(f"{path.stem}-u*.html"))
        if not pages:
            print(f"{config['site_name'][:24]:<24} (no cached page)")
            continue
        census = Census(config)
        for page in pages:
            census.sources.append(page.name)
            census.add_page(page.read_text())
        print("\n".join(format_report(census)) if full else format_all_line(census))


if __name__ == "__main__":
    main(sys.argv[1:])
