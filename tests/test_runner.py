"""Tests for scraper.runner.run_site and run_all_sites."""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scraper import db
from scraper.runner import run_site, run_all_sites

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(source_url="https://example.fi/shop/", max_pages=1, extra=None):
    cfg = {
        "site_name": "Test Shop",
        "source_url": source_url,
        "method": "css",
        "selectors": {
            "product_container": "li.product",
            "product_name": "h2",
            "price": ".price",
            "in_stock": None,
            "product_url": "a",
        },
        "pagination": {"type": "none", "max_pages": max_pages},
    }
    if extra:
        cfg.update(extra)
    return cfg


def _products(n=2):
    return [
        {"raw_name": f"Product {i}", "price": 9.99, "currency": "EUR",
         "in_stock": True, "product_url": "https://example.fi/p"}
        for i in range(n)
    ]


# ── run_site: happy path ──────────────────────────────────────────────────────

def test_run_site_writes_readings(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(3)):
        run_site(cfg, conn)

    rows = conn.execute("SELECT COUNT(*) FROM price_readings").fetchone()[0]
    assert rows == 3


def test_run_site_updates_health_success(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0
    assert site["last_scraped_at"] is not None


# ── run_site: empty page stops pagination ────────────────────────────────────

def test_run_site_stops_on_empty_page(conn):
    cfg = _cfg(max_pages=5)
    cfg["pagination"] = {
        "type": "url_pattern",
        "url_pattern": "https://example.fi/shop/page/{page}/",
        "max_pages": 5,
    }
    fetch_calls = []

    def fake_fetch(url, **kwargs):
        fetch_calls.append(url)
        return "<html>ok</html>"

    # page 1: 2 products, page 2: 0 products → stop
    scrape_calls = [_products(2), _products(0)]

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=scrape_calls), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    assert len(fetch_calls) == 2  # page 1 + page 2, then stopped


# ── run_site: zero products → health failure ─────────────────────────────────

def test_run_site_zero_products_marks_failure(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[]):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1


# ── run_site: exception marks failure without raising ────────────────────────

def test_run_site_exception_marks_failure_does_not_raise(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", side_effect=RuntimeError("boom")):
        run_site(cfg, conn)  # must not raise

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "boom" in (site["last_error"] or "")


# ── run_site: jitter between pages ───────────────────────────────────────────

def test_run_site_jitter_called_between_pages(conn):
    cfg = _cfg()
    cfg["pagination"] = {
        "type": "url_pattern",
        "url_pattern": "https://example.fi/shop/page/{page}/",
        "max_pages": 3,
    }
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)), \
         patch("scraper.runner.time.sleep") as mock_sleep:
        run_site(cfg, conn)

    # sleep called between page fetches, not before the first
    assert mock_sleep.call_count == 2


# ── run_site: currency SEK for .se, EUR for others ───────────────────────────

def test_run_site_currency_sek_for_se_domain(conn):
    cfg = _cfg(source_url="https://spelparken.se/collections/pokemon-booster-boxes")
    cfg["site_name"] = "Spelparken"

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT currency FROM price_readings").fetchone()
    assert row["currency"] == "SEK"


def test_run_site_currency_eur_for_fi_domain(conn):
    cfg = _cfg(source_url="https://example.fi/shop/")
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT currency FROM price_readings").fetchone()
    assert row["currency"] == "EUR"


# ── run_all_sites: disabled sites are skipped ────────────────────────────────

def test_run_all_sites_skips_disabled(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = db.get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()

    configs_dir = tmp_path / "site_configs"
    configs_dir.mkdir()

    import json
    (configs_dir / "enabled.fi.json").write_text(json.dumps(_cfg("https://enabled.fi/")))
    (configs_dir / "disabled.fi.json").write_text(json.dumps({**_cfg("https://disabled.fi/"), "disabled": True}))

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)), \
         patch("scraper.runner.time.sleep"):
        run_all_sites(db_path, configs_dir=str(configs_dir))

    conn = db.get_connection(db_path)
    sites = conn.execute("SELECT name FROM sites").fetchall()
    names = [r["name"] for r in sites]
    assert "Test Shop" in names  # enabled site was scraped
    # disabled site never upserted / scraped
    enabled_rows = conn.execute("SELECT COUNT(*) FROM price_readings").fetchone()[0]
    assert enabled_rows == 1


# ── run_site: None-price products skipped, valid ones written ────────────────

def test_run_site_skips_none_price_products(conn):
    cfg = _cfg()
    products_with_none = [
        {"raw_name": "Sealed Box", "price": 49.90, "currency": "EUR", "in_stock": True, "product_url": ""},
        {"raw_name": "Single Card", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products_with_none):
        run_site(cfg, conn)

    rows = conn.execute("SELECT COUNT(*) FROM price_readings").fetchone()[0]
    assert rows == 1  # only the valid-price product written

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0  # partial success = healthy
    assert site["null_price_count"] == 1


def test_run_site_all_none_prices_marks_failure(conn):
    cfg = _cfg()
    all_none = [
        {"raw_name": "Single A", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
        {"raw_name": "Single B", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=all_none):
        run_site(cfg, conn)

    rows = conn.execute("SELECT COUNT(*) FROM price_readings").fetchone()[0]
    assert rows == 0

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert site["null_price_count"] == 2


def test_run_site_clean_run_resets_null_price_count(conn):
    cfg = _cfg()
    # first run: one skipped
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[
             {"raw_name": "Box", "price": 49.90, "currency": "EUR", "in_stock": True, "product_url": ""},
             {"raw_name": "Card", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
         ]):
        run_site(cfg, conn)

    # second run: all valid
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(2)):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["null_price_count"] == 0


# ── run_all_sites: one site exception does not abort others ──────────────────

def test_run_all_sites_exception_does_not_abort_others(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = db.get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()

    configs_dir = tmp_path / "site_configs"
    configs_dir.mkdir()

    import json
    cfg_a = {**_cfg("https://site-a.fi/"), "site_name": "Site A"}
    cfg_b = {**_cfg("https://site-b.fi/"), "site_name": "Site B"}
    (configs_dir / "a.fi.json").write_text(json.dumps(cfg_a))
    (configs_dir / "b.fi.json").write_text(json.dumps(cfg_b))

    call_count = {"n": 0}

    def fetch_side_effect(url, **kwargs):
        call_count["n"] += 1
        if "site-a" in url:
            raise RuntimeError("site A exploded")
        return "<html>ok</html>"

    with patch("scraper.runner.fetch", side_effect=fetch_side_effect), \
         patch("scraper.runner.scrape_page", return_value=_products(1)), \
         patch("scraper.runner.time.sleep"):
        run_all_sites(db_path, configs_dir=str(configs_dir))

    conn = db.get_connection(db_path)
    # Site B succeeded
    rows = conn.execute(
        "SELECT COUNT(*) FROM price_readings pr JOIN sites s ON s.id=pr.site_id WHERE s.name='Site B'"
    ).fetchone()[0]
    assert rows == 1
