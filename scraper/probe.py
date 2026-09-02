"""Availability probe — what a site's stock badges actually say.

Operator tool, run by hand while writing a config's availability block. It is
not part of a scrape run and writes nothing to the database.

    python -m scraper.probe site_configs/tcgkauppa.fi.json
    python -m scraper.probe site_configs/tcgkauppa.fi.json --url 3 --limit 10
    python -m scraper.probe site_configs/tcgkauppa.fi.json --html-file page.html
    python -m scraper.probe --all
"""
import argparse
import glob
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import soupsieve
from bs4 import BeautifulSoup, Tag

from scraper.fetcher import FetchError, fetch
from scraper.paginator import source_urls
from scraper.parser import (
    AVAILABILITY_STATES,
    availability_forms,
    find_containers,
    scrape_page,
)

# Where shops tend to hang a stock badge. Probed alongside the configured
# availability.selector, so an unmapped badge shows up without reading page
# source. saatav/ennakko catch the Finnish wordings ("Saatavuus", "Ennakko").
HEURISTIC_SELECTORS = (
    '[class*="stock"]',
    '[class*="avail"]',
    '[class*="badge"]',
    '[class*="saatav"]',
    '[class*="ennakko"]',
)

# One badge text per line, so long marketing copy must not wrap the report.
TEXT_CAP = 80

# Themes that put the post id in the container's class list give every listing
# a distinct class list, which would print 48 near-identical rows.
MAX_CENSUS_ROWS = 12


def configured_selectors(config: dict) -> "list[str]":
    """Every selector the config's availability block actually reads.

    `presence` carries its own selector and falls back to the block-level one,
    which is where 14 of the configs keep the selector that decides their state.
    """
    block = config.get("availability") or {}
    if not isinstance(block, dict):
        return []
    presence = block.get("presence")
    candidates = [block.get("selector")]
    if isinstance(presence, dict):
        candidates.append(presence.get("selector") or block.get("selector"))

    selectors = []
    for selector in candidates:
        if selector and selector not in selectors:
            selectors.append(selector)
    return selectors


def _badge_selectors(config: dict) -> "list[str]":
    """The configured selectors first, then the heuristics."""
    selectors = configured_selectors(config)
    return selectors + [s for s in HEURISTIC_SELECTORS if s not in selectors]


def _valid_only(selectors: "list[str]", errors: "list[str]") -> "list[str]":
    """Drop selectors soupsieve cannot compile, naming each in errors.

    A hand-edited selector with an unbalanced bracket is the config bug this
    tool gets run to find, so it must report it rather than raise mid-report.
    """
    ok = []
    for selector in selectors:
        try:
            soupsieve.compile(selector)
        except Exception as exc:
            errors.append(f"selector {selector!r} is not valid CSS — {_describe(exc)}")
        else:
            ok.append(selector)
    return ok


def _is_stock_attr(name: str) -> bool:
    name = name.lower()
    return name.startswith("data-") and ("avail" in name or "stock" in name)


def _clean(text: str) -> str:
    return " ".join(text.split())[:TEXT_CAP]


def _describe(exc: Exception) -> str:
    """Type plus first line of the message. soupsieve's runs to five lines."""
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    return f"{type(exc).__name__}: {_clean(first_line)}"


class Census:
    """What one probe run learned about a site's availability badges.

    Counts accumulate across pages, because a site's listings are split over
    several source URLs and one URL's split says little about the site.
    """

    def __init__(self, config: dict, limit: int = 5):
        self.config = config
        self.limit = limit
        self.site_name = config.get("site_name", "(unnamed)")
        self.forms = availability_forms(config)
        self.errors: "list[str]" = []
        self.badge_selectors = _valid_only(_badge_selectors(config), self.errors)
        self.pages = 0
        self.listings = 0
        self.class_lists: Counter = Counter()
        self.class_tokens: Counter = Counter()
        self.badge_text: "dict[str, Counter]" = {
            sel: Counter() for sel in self.badge_selectors
        }
        self.data_values: "dict[str, Counter]" = defaultdict(Counter)
        self.sources: "list[str]" = []
        self.split: Counter = Counter()
        self.samples: "dict[str, list[tuple[str, Optional[str]]]]" = defaultdict(list)

    @property
    def unknown_share(self) -> float:
        """Percentage of this run's listings the config could not resolve."""
        if not self.listings:
            return 0.0
        return 100.0 * self.split.get("unknown", 0) / self.listings

    def add_error(self, message: str) -> None:
        """Record a problem once, however many pages hit it."""
        if message not in self.errors:
            self.errors.append(message)

    def add_page(self, html: str) -> None:
        self.pages += 1

        try:
            containers = find_containers(BeautifulSoup(html, "html.parser"), self.config)
        except Exception as exc:
            self.add_error(f"product_container selector failed — {_describe(exc)}")
            containers = []
        for container in containers:
            self._add_container(container)

        # A broken selector anywhere in the config raises here. That is the bug
        # the operator came to find, so the census above still gets printed.
        try:
            products = scrape_page(html, self.config)
        except Exception as exc:
            self.add_error(f"this config cannot parse the page — {_describe(exc)}")
            return

        self.listings += len(products)
        for product in products:
            state = product["availability"]
            self.split[state] += 1
            self._add_sample(state, product)

    def _add_container(self, container: Tag) -> None:
        classes = container.get("class") or []
        self.class_lists[" ".join(classes) or "(no class)"] += 1
        self.class_tokens.update(classes)

        for selector in self.badge_selectors:
            for el in container.select(selector):
                self.badge_text[selector][_clean(el.get_text()) or "(empty)"] += 1

        # The container's own attributes count too: karkkainen.com carries
        # data-ls-* on the container, not on a nested badge.
        for el in [container, *container.find_all(True)]:
            for name, value in el.attrs.items():
                if not _is_stock_attr(name):
                    continue
                if isinstance(value, list):
                    value = " ".join(value)
                self.data_values[name][_clean(str(value)) or "(empty)"] += 1

    def _add_sample(self, state: str, product: dict) -> None:
        """Keep up to `limit` distinct names per state, first sighting wins."""
        samples = self.samples[state]
        if len(samples) >= self.limit:
            return
        name = product["raw_name"] or "(no name)"
        if any(name == seen for seen, _ in samples):
            return
        samples.append((name, product["availability_text"]))


def unmatched_selectors(census: Census) -> "list[str]":
    """Configured selectors that matched no element on any page.

    This is the failure the probe exists to catch: a `presence` selector that
    matches nothing reads every listing as its `absent` state, and a `text_map`
    selector that matches nothing reads every listing as the `default`. Either
    way the split looks confident and fully resolved. A negative marker such as
    `.out-of-stock` legitimately matches nothing on an all-in-stock page, so
    this is a prompt to check the page, not proof of a broken config.
    """
    if not census.listings:
        return []
    return [s for s in configured_selectors(census.config) if not census.badge_text.get(s)]


def _rows(counter: Counter, indent: str = "    ", width: int = TEXT_CAP) -> "list[str]":
    """Counter as `  42x value` lines, biggest first, capped."""
    if not counter:
        return [f"{indent}(none)"]
    ordered = counter.most_common()
    lines = [
        f"{indent}{count:>5}x  {_ellipsis(value, width)}"
        for value, count in ordered[:MAX_CENSUS_ROWS]
    ]
    hidden = len(ordered) - MAX_CENSUS_ROWS
    if hidden > 0:
        lines.append(f"{indent}       … {hidden} more distinct value(s)")
    return lines


def _ellipsis(value: str, width: int) -> str:
    return value if len(value) <= width else value[:width] + "…"


def format_report(census: Census) -> "list[str]":
    """The full single-site report as printable lines."""
    out = [
        f"{census.site_name} — {census.listings} listing(s) over {census.pages} page(s)",
        f"  availability forms: {census.forms or '(none — everything reads as unknown)'}",
        f"  read: {_sources_text(census)}",
    ]

    for selector in unmatched_selectors(census):
        out.append(
            f"  NO MATCHES: configured selector {selector!r} matched nothing on "
            f"{census.listings} listing(s), so every listing fell back — which is "
            f"also what a wrong selector looks like"
        )

    for error in census.errors:
        out.append(f"  problem: {error}")

    # Tokens come first because a WooCommerce theme stamps the post id into the
    # class list, so every listing has a distinct list and only the token counts
    # show which class tracks stock.
    out.append("")
    out.append("  container class tokens:")
    out += _rows(census.class_tokens, indent="    ")
    out.append("  container class lists:")
    out += _rows(census.class_lists, indent="    ", width=140)

    out.append("")
    out.append("  badge text by selector (counts are matched elements, not listings):")
    configured = configured_selectors(census.config)
    for selector in census.badge_selectors:
        label = f"{selector}{'  (configured)' if selector in configured else ''}"
        out.append(f"    {label}")
        out += _rows(census.badge_text[selector], indent="      ")

    out.append("")
    out.append("  data-* attributes matching avail/stock:")
    if not census.data_values:
        out.append("    (none)")
    for name in sorted(census.data_values):
        out.append(f"    {name}")
        out += _rows(census.data_values[name], indent="      ")

    out.append("")
    out.append(f"  split: {_split_text(census)}")
    out.append(f"  unknown share: {census.unknown_share:.1f}%")

    out.append("")
    out.append(f"  samples (up to {census.limit} per state):")
    for state in AVAILABILITY_STATES:
        samples = census.samples.get(state)
        if not samples:
            continue
        out.append(f"    {state}")
        for name, text in samples:
            # No text means the default fired, or a matched element had no text
            # of its own (an icon-only sold-out marker). detect_availability
            # records both as NULL, so the report must not claim which it was.
            badge = f'  ← "{_ellipsis(text, 48)}"' if text else "  ← (no badge text)"
            out.append(f"      {_ellipsis(name, 70)}{badge}")

    return out


def _sources_text(census: Census) -> str:
    """What the numbers came from. Listed in full up to three, then counted."""
    if not census.sources:
        return "nothing"
    if len(census.sources) <= 3:
        return ", ".join(census.sources)
    return f"page 1 of {len(census.sources)} source URLs"


def _split_text(census: Census) -> str:
    parts = []
    for state in AVAILABILITY_STATES:
        count = census.split.get(state, 0)
        share = 100.0 * count / census.listings if census.listings else 0.0
        parts.append(f"{state}={count} ({share:.0f}%)")
    return "  ".join(parts)


def format_all_line(census: Census) -> str:
    """One line per site for --all: the acceptance check for ticket 18."""
    split = " ".join(
        f"{state}={census.split.get(state, 0)}" for state in AVAILABILITY_STATES
    )
    line = (
        f"{census.site_name[:24]:<24} {census.listings:>5} listings  "
        f"{split:<58} unknown {census.unknown_share:>5.1f}%  "
        f"{census.forms or '(none)'}"
    )
    for selector in unmatched_selectors(census):
        line += f"  [no matches: {selector}]"
    for error in census.errors:
        line += f"  [{error}]"
    return line


def _sleep_jitter() -> None:
    """The scraper's inter-fetch pause. A probe is no excuse to hammer a shop."""
    time.sleep(random.uniform(1, 4))


def probe_site(
    config: dict,
    url_index: Optional[int] = None,
    html_file: Optional[str] = None,
    limit: int = 5,
    sleep_first: bool = False,
) -> Census:
    """Census one site: page 1 of each of its URLs, or a saved HTML file.

    url_index is 1-based, counted in the order the config lists its URLs.
    html_file skips the network entirely, which is how the tests run.
    """
    census = Census(config, limit=limit)

    if html_file:
        census.sources.append(html_file)
        census.add_page(Path(html_file).read_text())
        return census

    urls = source_urls(config)
    if url_index is not None:
        urls = [urls[url_index - 1]]

    for i, url in enumerate(urls):
        if sleep_first or i > 0:
            _sleep_jitter()
        try:
            html = fetch(url, config)
        except (FetchError, NotImplementedError) as exc:
            census.add_error(str(exc))
            continue
        census.sources.append(url)
        census.add_page(html)

    return census


def load_configs(configs_dir: str) -> "list[dict]":
    """Every non-disabled config in configs_dir, in filename order."""
    configs = []
    for path in sorted(glob.glob(f"{configs_dir}/*.json")):
        try:
            config = json.loads(Path(path).read_text())
        except Exception as exc:
            print(f"failed to load {path}: {exc}")
            continue
        if config.get("disabled"):
            continue
        configs.append(config)
    return configs


def probe_all(configs_dir: str, limit: int = 5) -> int:
    configs = load_configs(configs_dir)
    if not configs:
        print(f"no configs found in {configs_dir}")
        return 1

    for i, config in enumerate(configs):
        census = probe_site(config, limit=limit, sleep_first=i > 0)
        print(format_all_line(census), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.probe",
        description="Report what a site's availability badges say and how the "
                    "config reads them.",
    )
    parser.add_argument("config", nargs="?", help="path to a site config JSON")
    parser.add_argument(
        "--all", action="store_true",
        help="one coverage line per non-disabled config (fetches every site)",
    )
    parser.add_argument(
        "--url", type=int, metavar="N",
        help="probe only the site's Nth source URL, counting from 1",
    )
    parser.add_argument("--html-file", metavar="PATH", help="read saved HTML, no network")
    parser.add_argument(
        "--limit", type=int, default=5, metavar="N",
        help="sample names printed per availability state (default 5)",
    )
    parser.add_argument("--configs-dir", default="site_configs")
    return parser


def main(argv: "Optional[list[str]]" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.all:
        return probe_all(args.configs_dir, limit=args.limit)

    if not args.config:
        parser.error("give a config path, or --all")

    config = json.loads(Path(args.config).read_text())

    if args.url is not None and not args.html_file:
        urls = source_urls(config)
        if not 1 <= args.url <= len(urls):
            parser.error(f"--url must be between 1 and {len(urls)} for this config")

    census = probe_site(
        config, url_index=args.url, html_file=args.html_file, limit=args.limit
    )
    print("\n".join(format_report(census)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    sys.exit(main())
