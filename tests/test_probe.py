"""Tests for the availability probe CLI. No network: every case uses --html-file."""
import json
from pathlib import Path

import pytest

from scraper import probe
from scraper.fetcher import FetchError
from scraper.probe import Census, format_all_line, main, probe_site

TCGKAUPPA_CONFIG = "site_configs/tcgkauppa.fi.json"
TCGKAUPPA_FIXTURE = "tests/fixtures/tcgkauppa.fi/page1.html"
KARKKAINEN_CONFIG = "site_configs/karkkainen.com.json"
KARKKAINEN_FIXTURE = "tests/fixtures/karkkainen.com/page1.html"
PRISMA_FIXTURE = "tests/fixtures/prisma.fi/page1.html"


def census_for(config_path: str, fixture: str, limit: int = 5) -> Census:
    config = json.loads(Path(config_path).read_text())
    return probe_site(config, html_file=fixture, limit=limit)


def test_html_file_split_matches_the_config():
    """tcgkauppa's container_class_map resolves every listing on the fixture."""
    census = census_for(TCGKAUPPA_CONFIG, TCGKAUPPA_FIXTURE)
    assert census.listings == 48
    assert census.split["in_stock"] == 6
    assert census.split["out_of_stock"] == 42
    assert census.split["unknown"] == 0
    assert census.unknown_share == 0.0
    assert census.forms == "container_class_map"


def test_html_file_badge_census():
    census = census_for(TCGKAUPPA_CONFIG, TCGKAUPPA_FIXTURE)
    # The class tokens are what the config's map keys off.
    assert census.class_tokens["instock"] == 6
    assert census.class_tokens["outofstock"] == 42
    # Heuristic selectors find the badge text the site prints for out-of-stock.
    assert census.badge_text['[class*="stock"]']["Ei varastossa"] == 42
    assert census.badge_text['[class*="saatav"]'] == {}
    # WooCommerce puts stock in the class list, so there is no data-* to find.
    assert census.data_values == {}


def test_data_attribute_census():
    """karkkainen.com carries stock in data-ls-availability, not in a class."""
    census = census_for(KARKKAINEN_CONFIG, KARKKAINEN_FIXTURE)
    assert census.data_values["data-ls-availability"]["OutOfStock"] == 60


def test_samples_are_capped_per_state():
    census = census_for(TCGKAUPPA_CONFIG, TCGKAUPPA_FIXTURE, limit=2)
    assert [len(v) for v in census.samples.values()] == [2, 2]
    names = [name for name, _ in census.samples["in_stock"]]
    assert all(names)
    assert len(set(names)) == 2


def test_cli_prints_split_and_unknown_share(capsys):
    exit_code = main([TCGKAUPPA_CONFIG, "--html-file", TCGKAUPPA_FIXTURE, "--limit", "2"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "TCG-kauppa — 48 listing(s) over 1 page(s)" in out
    assert "availability forms: container_class_map" in out
    assert "split: in_stock=6 (12%)  out_of_stock=42 (88%)" in out
    assert "unknown share: 0.0%" in out
    assert "42x  Ei varastossa" in out
    assert "42x  outofstock" in out
    # Samples name the listing and the text that resolved it.
    assert "Pokémon Abyss Eye Japanese Booster (M5)" in out


def test_selector_that_matches_nothing_is_called_out(capsys, tmp_path):
    """A wrong selector produces a confident-looking split — every listing takes
    the default or the presence `absent` state — which is the failure the split
    alone cannot show.

    prisma.fi was that case until ticket 18 corrected the selector to
    `.bg-color-background-error`, so this rebuilds the broken config it had.
    """
    config = json.loads(Path("site_configs/prisma.fi.json").read_text())
    config["availability"]["selector"] = ".background-error p"
    broken = tmp_path / "prisma-broken.json"
    broken.write_text(json.dumps(config))

    census = probe_site(config, html_file=PRISMA_FIXTURE, limit=5)
    assert census.split["in_stock"] == 33
    assert census.unknown_share == 0.0
    assert probe.unmatched_selectors(census) == [".background-error p"]
    assert "[no matches: .background-error p]" in format_all_line(census)

    main([str(broken), "--html-file", PRISMA_FIXTURE])
    assert "NO MATCHES: configured selector '.background-error p'" in capsys.readouterr().out


def test_corrected_selector_reads_the_same_page_as_a_mix():
    """The same fixture under the shipped config: the marker goes away and the
    sold-out cards show up. The exact split is pinned in
    tests/test_availability_configs.py."""
    census = census_for("site_configs/prisma.fi.json", PRISMA_FIXTURE)
    assert census.split["out_of_stock"] > 0
    assert probe.unmatched_selectors(census) == []


def test_working_selector_is_not_called_out():
    census = census_for("site_configs/peliparatiisi.net.json",
                        "tests/fixtures/peliparatiisi.net/page1.html")
    assert probe.unmatched_selectors(census) == []
    assert "[no matches" not in format_all_line(census)


def test_presence_selector_is_probed_and_labelled(capsys):
    """A presence block keeps its selector under presence.selector, not at the top,
    so both it and the block's top-level text_map selector get probed."""
    config_path = "site_configs/poromagia.com.json"
    census = census_for(config_path, "tests/fixtures/poromagia.com/page1.html")
    assert probe.configured_selectors(census.config) == ["p.availability",
                                                        ".instock.availability"]
    assert census.badge_text[".instock.availability"]

    main([config_path, "--html-file", "tests/fixtures/poromagia.com/page1.html"])
    out = capsys.readouterr().out
    assert ".instock.availability  (configured)" in out
    assert "NO MATCHES" not in out


def test_all_line_reports_split_and_forms():
    census = census_for(TCGKAUPPA_CONFIG, TCGKAUPPA_FIXTURE)
    line = format_all_line(census)
    assert "TCG-kauppa" in line
    assert "48 listings" in line
    assert "in_stock=6 out_of_stock=42 preorder=0 unknown=0" in line
    assert "unknown   0.0%" in line
    assert line.endswith("container_class_map")


def test_untracked_site_reads_as_all_unknown():
    config = {
        "site_name": "No badges",
        "source_url": "https://example.test/",
        "selectors": {"product_container": "li", "product_name": "a"},
    }
    census = Census(config)
    census.add_page("<ul><li><a>Booster box</a></li><li><a>ETB</a></li></ul>")
    assert census.forms is None
    assert census.split["unknown"] == 2
    assert census.unknown_share == 100.0


def test_all_skips_disabled_configs_and_reports_fetch_errors(tmp_path, monkeypatch, capsys):
    """--all covers one line per live site; a dead site still gets its line."""
    html = Path(TCGKAUPPA_FIXTURE).read_text()
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    live = json.loads(Path(TCGKAUPPA_CONFIG).read_text())
    live["source_urls"] = live["source_urls"][:1]
    (configs_dir / "live.json").write_text(json.dumps(live))
    (configs_dir / "dead.json").write_text(json.dumps({
        **live, "site_name": "Dead shop", "source_urls": ["https://dead.test/"],
    }))
    (configs_dir / "off.json").write_text(json.dumps({**live, "disabled": True}))

    def fake_fetch(url, config=None):
        if "dead.test" in url:
            raise FetchError("HTTP 503 for " + url, 503)
        return html

    monkeypatch.setattr(probe, "fetch", fake_fetch)
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)

    exit_code = probe.probe_all(str(configs_dir))
    lines = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 0
    assert len(lines) == 2
    assert "Dead shop" in lines[0] and "0 listings" in lines[0]
    assert "[HTTP 503 for https://dead.test/]" in lines[0]
    assert "TCG-kauppa" in lines[1] and "48 listings" in lines[1]


def test_invalid_css_selector_is_reported_not_raised(capsys):
    """A hand-edited selector with a syntax error is what the probe is run to find."""
    config = {
        "site_name": "Broken selector",
        "availability": {"selector": "span[class=", "text_map": {"Loppu": "out_of_stock"}},
        "selectors": {"product_container": "li", "product_name": "a"},
    }
    census = Census(config)
    census.add_page("<ul><li><a>Booster box</a></li></ul>")

    report = "\n".join(probe.format_report(census))
    assert "problem: selector 'span[class=' is not valid CSS" in report
    # The parser raises on the same selector, and the report says so instead of
    # the traceback the operator would otherwise get.
    assert "problem: this config cannot parse the page — SelectorSyntaxError" in report
    # The container census still ran: only the availability read was broken.
    assert census.class_lists["(no class)"] == 1


def test_url_out_of_range_is_rejected():
    with pytest.raises(SystemExit):
        main([TCGKAUPPA_CONFIG, "--url", "99"])
