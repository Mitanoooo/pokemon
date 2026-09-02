"""Ticket 18 helper: cut a cached page down to a small availability fixture.

    venv/bin/python .scratch/tracker-refocus/trim_fixture.py <site> <cached.html> [per_state]

Keeps up to `per_state` product containers per resulting availability state (4 by
default) and drops script/style/noscript/svg, so a fixture that guards one
site's mapping is a few kB instead of the several hundred kB a whole saved page
costs. Writes tests/fixtures/<site>/availability.html and prints the split.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup  # noqa: E402

from scraper.parser import detect_availability, find_containers, scrape_page  # noqa: E402

PAGES = Path(__file__).parent / "pages"
DROP = ("script", "style", "noscript", "svg")


def ancestor_shells(container, out):
    """Empty copies of the container's ancestors, outermost first.

    A container selector such as "ul.products li.product" only matches when the
    ancestors are there, so the fixture keeps the chain as empty tags.
    """
    shells = []
    for parent in container.parents:
        if parent.name in ("body", "html", "[document]"):
            break
        shells.append(out.new_tag(parent.name, attrs=parent.attrs))
    return list(reversed(shells))


def main():
    site, source = sys.argv[1], sys.argv[2]
    per_state = int(sys.argv[3]) if len(sys.argv) > 3 else 4

    config = json.loads(Path(f"site_configs/{site}.json").read_text())
    html = (PAGES / source).read_text()
    soup = BeautifulSoup(html, "html.parser")

    kept = defaultdict(list)
    for container in find_containers(soup, config):
        state, _ = detect_availability(container, config)
        if len(kept[state]) < per_state:
            kept[state].append(container)

    out = BeautifulSoup("<html><body></body></html>", "html.parser")
    slot = out.body
    for shell in ancestor_shells(next(iter(kept.values()))[0], out):
        slot.append(shell)
        slot = shell
    for state in sorted(kept):
        for container in kept[state]:
            for junk in container.find_all(DROP):
                junk.decompose()
            slot.append(container)

    target = Path("tests/fixtures") / site / "availability.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(out) + "\n", encoding="utf-8")

    split = Counter(p["availability"] for p in scrape_page(target.read_text(), config))
    print(f"{target} {target.stat().st_size // 1024} kB  {dict(split)}")


if __name__ == "__main__":
    main()
