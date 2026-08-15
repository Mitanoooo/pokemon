"""Tests for scraper.runner.run_site and run_all_sites."""
import json
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


# ── run tracking ──────────────────────────────────────────────────────────────

def test_run_site_creates_scrape_run_row(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT * FROM scrape_runs").fetchone()
    assert row is not None
    assert row["started_at"] is not None
    assert row["finished_at"] is not None


def test_run_site_price_readings_carry_run_id(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(2)):
        run_site(cfg, conn)

    run_id = conn.execute("SELECT id FROM scrape_runs").fetchone()["id"]
    run_ids = [r["run_id"] for r in conn.execute("SELECT run_id FROM price_readings").fetchall()]
    assert run_ids == [run_id, run_id]


def test_run_site_uses_supplied_run_id_without_creating_a_run(conn):
    cfg = _cfg()
    run_id = db.start_run(conn)

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn, run_id=run_id)

    assert conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0] == 1
    assert conn.execute("SELECT run_id FROM price_readings").fetchone()["run_id"] == run_id


def test_run_all_sites_creates_one_finished_run_shared_by_all_sites(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = db.get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()

    configs_dir = tmp_path / "site_configs"
    configs_dir.mkdir()

    (configs_dir / "a.fi.json").write_text(
        json.dumps({**_cfg("https://site-a.fi/"), "site_name": "Site A"}))
    (configs_dir / "b.fi.json").write_text(
        json.dumps({**_cfg("https://site-b.fi/"), "site_name": "Site B"}))

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)), \
         patch("scraper.runner.time.sleep"):
        run_all_sites(db_path, configs_dir=str(configs_dir))

    conn = db.get_connection(db_path)
    runs = conn.execute("SELECT * FROM scrape_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["started_at"] is not None
    assert runs[0]["finished_at"] is not None

    run_ids = {r["run_id"] for r in conn.execute("SELECT run_id FROM price_readings").fetchall()}
    assert run_ids == {runs[0]["id"]}


# ── listings persistence ──────────────────────────────────────────────────────

def test_run_site_upserts_listing_for_every_product(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(3)):
        run_site(cfg, conn)

    names = [r["raw_name"] for r in conn.execute(
        "SELECT raw_name FROM listings ORDER BY raw_name").fetchall()]
    assert names == ["Product 0", "Product 1", "Product 2"]


def test_run_site_upserts_listing_for_price_less_product(conn):
    cfg = _cfg()
    products = [
        {"raw_name": "Sealed Box", "price": 49.90, "currency": "EUR", "in_stock": True,
         "product_url": "https://example.fi/p/box"},
        {"raw_name": "Single Card", "price": None, "currency": "EUR", "in_stock": True,
         "product_url": "https://example.fi/p/card"},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products):
        run_site(cfg, conn)

    listing = conn.execute(
        "SELECT * FROM listings WHERE raw_name = 'Single Card'").fetchone()
    assert listing is not None
    assert listing["latest_price"] is None
    assert listing["product_url"] == "https://example.fi/p/card"

    # …but it stays out of price_readings
    reading_names = [r["raw_name"] for r in conn.execute(
        "SELECT raw_name FROM price_readings").fetchall()]
    assert reading_names == ["Sealed Box"]


def test_run_site_listings_carry_last_run_id(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    run_id = conn.execute("SELECT id FROM scrape_runs").fetchone()["id"]
    assert conn.execute("SELECT last_run_id FROM listings").fetchone()["last_run_id"] == run_id


def test_run_site_second_run_keeps_first_seen_and_moves_last_seen(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    conn.execute("UPDATE listings SET first_seen_at='2020-01-01 00:00:00', last_seen_at='2020-01-01 00:00:00'")
    conn.commit()

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    rows = conn.execute("SELECT * FROM listings").fetchall()
    assert len(rows) == 1
    assert rows[0]["first_seen_at"] == "2020-01-01 00:00:00"
    assert rows[0]["last_seen_at"] > "2020-01-01 00:00:00"


def test_run_site_resolves_relative_product_url_against_source_url(conn):
    cfg = _cfg(source_url="https://example.fi/shop/")
    products = [
        {"raw_name": "Relative Box", "price": 10.0, "currency": "EUR", "in_stock": True,
         "product_url": "/products/relative-box"},
        {"raw_name": "Sibling Box", "price": 11.0, "currency": "EUR", "in_stock": True,
         "product_url": "sibling-box"},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products):
        run_site(cfg, conn)

    urls = {r["raw_name"]: r["product_url"] for r in conn.execute(
        "SELECT raw_name, product_url FROM listings").fetchall()}
    assert urls["Relative Box"] == "https://example.fi/products/relative-box"
    assert urls["Sibling Box"] == "https://example.fi/shop/sibling-box"


def test_run_site_leaves_absolute_product_url_untouched(conn):
    cfg = _cfg(source_url="https://example.fi/shop/")
    products = [
        {"raw_name": "Absolute Box", "price": 10.0, "currency": "EUR", "in_stock": True,
         "product_url": "https://cdn.example.com/p/abs"},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products):
        run_site(cfg, conn)

    row = conn.execute("SELECT product_url FROM listings").fetchone()
    assert row["product_url"] == "https://cdn.example.com/p/abs"


def test_run_site_missing_product_url_stored_as_null_not_source_url(conn):
    cfg = _cfg(source_url="https://example.fi/shop/")
    products = [
        {"raw_name": "No Link Box", "price": 10.0, "currency": "EUR", "in_stock": True,
         "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products):
        run_site(cfg, conn)

    row = conn.execute("SELECT product_url FROM listings").fetchone()
    assert row["product_url"] is None


def test_run_site_all_none_prices_still_upserts_listings(conn):
    cfg = _cfg()
    all_none = [
        {"raw_name": "Single A", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
        {"raw_name": "Single B", "price": None, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=all_none):
        run_site(cfg, conn)

    # site is marked unhealthy, but the sightings are still recorded so they do
    # not look brand new on the next run
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM price_readings").fetchone()[0] == 0


def test_run_site_listing_product_id_resolved_from_name_mappings(conn):
    cfg = _cfg()
    conn.execute(
        """
        INSERT INTO cardmarket_products (id, name, id_category, category_name, id_expansion)
        VALUES (500, 'Prismatic Evolutions ETB', 1, 'Elite Trainer Boxes', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO name_mappings (raw_name, cardmarket_product_id, status)
        VALUES ('Product 0', 500, 'mapped')
        """
    )
    conn.commit()

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT product_id FROM listings").fetchone()
    assert row["product_id"] == 500


# ── listings: real fixture + real site config ─────────────────────────────────

def test_run_site_resolves_real_relative_hrefs_to_absolute(conn):
    """Every configured site but tcgkauppa.fi emits root-relative hrefs, so the
    urljoin step is load-bearing in production — pin it against real HTML."""
    root = Path(__file__).parent.parent
    cfg = json.loads((root / "site_configs" / "spelparken.se.json").read_text())
    html = (root / "tests" / "fixtures" / "spelparken.se" / "page1.html").read_text()

    with patch("scraper.runner.fetch", return_value=html), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    rows = conn.execute("SELECT raw_name, product_url FROM listings").fetchall()
    assert rows, "fixture produced no listings"
    for r in rows:
        assert r["product_url"].startswith("https://spelparken.se/products/"), r["raw_name"]
