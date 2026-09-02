"""Tests for scraper.runner.run_site and run_all_sites."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scraper import db
from scraper.fetcher import FetchError
from scraper.runner import run_site, run_all_sites

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(source_url="https://example.fi/shop/", max_pages=1, extra=None,
         source_urls=None):
    cfg = {
        "site_name": "Test Shop",
        "source_url": source_url,
        "method": "css",
        "selectors": {
            "product_container": "li.product",
            "product_name": "h2",
            "price": ".price",
            "product_url": "a",
        },
        "pagination": {"type": "none", "max_pages": max_pages},
    }
    if source_urls:
        del cfg["source_url"]
        cfg["source_urls"] = source_urls
    if extra:
        cfg.update(extra)
    return cfg


def _products(n=2):
    return [
        {"raw_name": f"Product {i}", "price": 9.99, "currency": "EUR",
         "availability": "in_stock", "product_url": "https://example.fi/p"}
        for i in range(n)
    ]


# ── run_site: happy path ──────────────────────────────────────────────────────

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

    row = conn.execute("SELECT latest_currency FROM listings").fetchone()
    assert row["latest_currency"] == "SEK"


def test_run_site_currency_eur_for_fi_domain(conn):
    cfg = _cfg(source_url="https://example.fi/shop/")
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT latest_currency FROM listings").fetchone()
    assert row["latest_currency"] == "EUR"


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
    enabled_rows = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    assert enabled_rows == 1


# ── run_site: None-price products skipped, valid ones written ────────────────

def test_run_site_skips_none_price_products(conn):
    cfg = _cfg()
    products_with_none = [
        {"raw_name": "Sealed Box", "price": 49.90, "currency": "EUR", "availability": "in_stock", "product_url": ""},
        {"raw_name": "Single Card", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products_with_none):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0  # partial success = healthy
    assert site["null_price_count"] == 1


def test_run_site_all_none_prices_marks_failure(conn):
    cfg = _cfg()
    all_none = [
        {"raw_name": "Single A", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
        {"raw_name": "Single B", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=all_none):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert site["null_price_count"] == 2


def test_run_site_clean_run_resets_null_price_count(conn):
    cfg = _cfg()
    # first run: one skipped
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[
             {"raw_name": "Box", "price": 49.90, "currency": "EUR", "availability": "in_stock", "product_url": ""},
             {"raw_name": "Card", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
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
        "SELECT COUNT(*) FROM listings l JOIN sites s ON s.id=l.site_id WHERE s.name='Site B'"
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


def test_run_site_uses_supplied_run_id_without_creating_a_run(conn):
    cfg = _cfg()
    run_id = db.start_run(conn)

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn, run_id=run_id)

    assert conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0] == 1
    assert conn.execute("SELECT last_run_id FROM listings").fetchone()["last_run_id"] == run_id


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

    run_ids = {r["last_run_id"] for r in conn.execute("SELECT last_run_id FROM listings").fetchall()}
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
        {"raw_name": "Sealed Box", "price": 49.90, "currency": "EUR", "availability": "in_stock",
         "product_url": "https://example.fi/p/box"},
        {"raw_name": "Single Card", "price": None, "currency": "EUR", "availability": "in_stock",
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
        {"raw_name": "Relative Box", "price": 10.0, "currency": "EUR", "availability": "in_stock",
         "product_url": "/products/relative-box"},
        {"raw_name": "Sibling Box", "price": 11.0, "currency": "EUR", "availability": "in_stock",
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
        {"raw_name": "Absolute Box", "price": 10.0, "currency": "EUR", "availability": "in_stock",
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
        {"raw_name": "No Link Box", "price": 10.0, "currency": "EUR", "availability": "in_stock",
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
        {"raw_name": "Single A", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
        {"raw_name": "Single B", "price": None, "currency": "EUR", "availability": "in_stock", "product_url": ""},
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=all_none):
        run_site(cfg, conn)

    # site is marked unhealthy, but the sightings are still recorded so they do
    # not look brand new on the next run
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 2


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


# ── update event generation ───────────────────────────────────────────────────

def _run_once(cfg, conn, products):
    """One run of run_site serving the same product list on every page."""
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)


def _listing(name="Box", price=9.99, availability="in_stock", currency="EUR"):
    return {"raw_name": name, "price": price, "currency": currency,
            "availability": availability, "product_url": ""}


def _event_types(conn):
    return [r["event_type"] for r in conn.execute("SELECT event_type FROM updates")]


def test_run_site_first_run_emits_no_events_but_records_the_listings(conn):
    """Adding a shop must not bury the feed under its whole catalogue."""
    cfg = _cfg()
    _run_once(cfg, conn, _products(3))

    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM updates").fetchone()[0] == 0


def test_run_site_emits_new_listing_once_the_site_has_a_history(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing("Old Box")])
    _run_once(cfg, conn, [_listing("Old Box"), _listing("New Box", price=19.99)])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "new_listing"
    assert rows[0]["raw_name"] == "New Box"
    assert rows[0]["new_value"] == "19.99"


def test_run_site_first_sighting_of_a_preorder_emits_new_preorder_only(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing("Old Box")])
    _run_once(cfg, conn, [_listing("Old Box"),
                          _listing("Preorder Box", price=54.9, availability="preorder")])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "new_preorder"
    assert rows[0]["raw_name"] == "Preorder Box"
    assert rows[0]["new_value"] == "54.9"


def test_run_site_in_stock_to_preorder_emits_new_preorder(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing(availability="in_stock")])
    _run_once(cfg, conn, [_listing(availability="preorder")])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "new_preorder"
    # Same payload shape as a first-sighting preorder: the price, nothing else
    assert rows[0]["old_value"] is None
    assert rows[0]["new_value"] == "9.99"


def test_run_site_out_of_stock_to_in_stock_emits_back_in_stock(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing(availability="out_of_stock")])
    _run_once(cfg, conn, [_listing(availability="in_stock")])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "back_in_stock"
    assert rows[0]["old_value"] == "out_of_stock"


def test_run_site_preorder_to_in_stock_emits_back_in_stock_naming_the_preorder(conn):
    """Release day: the old state is what separates this from an ordinary restock."""
    cfg = _cfg()
    _run_once(cfg, conn, [_listing(availability="preorder")])
    _run_once(cfg, conn, [_listing(availability="in_stock")])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "back_in_stock"
    assert rows[0]["old_value"] == "preorder"


def _event_names(conn):
    return [r["raw_name"] for r in conn.execute("SELECT raw_name FROM updates")]


def test_run_site_no_event_for_a_transition_out_of_unknown(conn):
    """The control listing differs only in its old state, so it pins the rule."""
    cfg = _cfg()
    _run_once(cfg, conn, [_listing("Unreadable", availability="unknown"),
                          _listing("Sold Out", availability="out_of_stock")])
    _run_once(cfg, conn, [_listing("Unreadable", availability="in_stock"),
                          _listing("Sold Out", availability="in_stock")])

    assert _event_names(conn) == ["Sold Out"]


def test_run_site_no_event_for_a_transition_into_unknown(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing("Badge Lost", availability="out_of_stock"),
                          _listing("Restocked", availability="out_of_stock")])
    _run_once(cfg, conn, [_listing("Badge Lost", availability="unknown"),
                          _listing("Restocked", availability="in_stock")])

    assert _event_names(conn) == ["Restocked"]


def test_run_site_emits_price_rise_event_on_higher_price(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing(price=9.99)])
    _run_once(cfg, conn, [_listing(price=14.99)])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "price_rise"
    assert rows[0]["old_value"] == "9.99"
    assert rows[0]["new_value"] == "14.99"


def test_run_site_emits_price_drop_event_on_lower_price(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing(price=9.99)])
    _run_once(cfg, conn, [_listing(price=7.49)])

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "price_drop"
    assert rows[0]["old_value"] == "9.99"
    assert rows[0]["new_value"] == "7.49"


def test_run_site_no_event_when_price_unchanged(conn):
    cfg = _cfg()
    _run_once(cfg, conn, [_listing("Steady"), _listing("Cheaper")])
    # The second listing moves, so an empty feed here would fail the test too
    _run_once(cfg, conn, [_listing("Steady"), _listing("Cheaper", price=5.0)])

    assert _event_names(conn) == ["Cheaper"]


def _sek_cfg():
    cfg = _cfg(source_url="https://spelparken.se/shop/")
    cfg["site_name"] = "Spelparken"
    return cfg


def test_run_site_price_event_threshold_is_1_for_sek(conn):
    cfg = _sek_cfg()
    _run_once(cfg, conn, [_listing(price=499.0, currency="SEK")])
    # 499.5 SEK is less than 1 SEK off, so no price event
    _run_once(cfg, conn, [_listing(price=499.5, currency="SEK")])

    assert _event_types(conn) == []


def test_run_site_price_event_threshold_fires_at_1_for_sek(conn):
    cfg = _sek_cfg()
    _run_once(cfg, conn, [_listing(price=499.0, currency="SEK")])
    # exactly 1 SEK off, which is the threshold
    _run_once(cfg, conn, [_listing(price=500.0, currency="SEK")])

    assert _event_types(conn) == ["price_rise"]


def test_run_site_stores_availability_and_its_text(conn):
    cfg = _cfg(extra={"availability": {"selector": ".badge",
                                       "text_map": {"Ennakkotilaus": "preorder"}}})
    products = [{"raw_name": "Box", "price": 9.99, "currency": "EUR",
                 "availability": "preorder",
                 "availability_text": "Ennakkotilaus 12.9.2026",
                 "product_url": ""}]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=products):
        run_site(cfg, conn)

    row = conn.execute("SELECT availability, availability_text FROM listings").fetchone()
    assert row["availability"] == "preorder"
    assert row["availability_text"] == "Ennakkotilaus 12.9.2026"


def test_run_site_records_the_configs_availability_forms_on_the_site(conn):
    cfg = _cfg(extra={"availability": {
        "selector": ".badge",
        "text_map": {"Loppu": "out_of_stock"},
        "presence": {"selector": ".cart", "present": "in_stock"},
    }})
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT availability_mode FROM sites WHERE name='Test Shop'").fetchone()
    assert row["availability_mode"] == "text_map,presence"


def test_run_site_leaves_availability_mode_null_for_an_untracked_site(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(1)):
        run_site(cfg, conn)

    row = conn.execute("SELECT availability_mode FROM sites WHERE name='Test Shop'").fetchone()
    assert row["availability_mode"] is None


def test_run_site_records_availability_mode_even_when_the_site_fails(conn):
    cfg = _cfg(extra={"availability": {"container_class_map": {"instock": "in_stock"}}})
    with patch("scraper.runner.fetch", side_effect=FetchError("HTTP 503")):
        run_site(cfg, conn)

    row = conn.execute(
        "SELECT availability_mode, consecutive_failures FROM sites WHERE name='Test Shop'"
    ).fetchone()
    assert row["availability_mode"] == "container_class_map"
    assert row["consecutive_failures"] == 1


def test_run_site_untracked_site_emits_no_transition_events_at_all(conn):
    """No availability block means every sighting reads unknown, run after run."""
    cfg = _cfg()  # real parser, no availability block
    page = ("<ul><li class='product'><h2>Box</h2>"
            "<span class='price'>9,99 €</span><a href='/p'>x</a></li></ul>")

    for _ in range(3):
        with patch("scraper.runner.fetch", return_value=page), \
             patch("scraper.runner.time.sleep"):
            run_site(cfg, conn)

    assert conn.execute("SELECT availability FROM listings").fetchone()[0] == "unknown"
    assert _event_types(conn) == []


# ── run_site: fetch failures surface the cause ────────────────────────────────

def test_run_site_fetch_error_message_lands_in_last_error(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch",
               side_effect=FetchError("HTTP 403 for https://example.fi/shop/")):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert "HTTP 403" in (site["last_error"] or "")
    assert site["consecutive_failures"] == 1


def test_run_site_network_error_message_lands_in_last_error(conn):
    cfg = _cfg()
    with patch("scraper.runner.fetch",
               side_effect=FetchError("ConnectTimeout: timed out for https://example.fi/shop/")):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert "ConnectTimeout" in (site["last_error"] or "")


# ── run_site: max_pages undercount warning ────────────────────────────────────

def _paginated_cfg(max_pages: int) -> dict:
    cfg = _cfg()
    cfg["pagination"] = {
        "type": "url_pattern",
        "url_pattern": "https://example.fi/shop/page/{page}/",
        "max_pages": max_pages,
    }
    return cfg


def test_run_site_warns_when_last_configured_page_still_had_products(conn, caplog):
    cfg = _paginated_cfg(2)
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(2)), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("max_pages" in m for m in warnings), warnings


def test_run_site_no_undercount_warning_when_pagination_stopped_early(conn, caplog):
    cfg = _paginated_cfg(3)
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=[_products(2), _products(0)]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert not any("max_pages" in m for m in warnings), warnings


def test_run_site_no_undercount_warning_when_last_page_is_partial(conn, caplog):
    """A shorter final page is the natural end of the listing, not an undercount."""
    cfg = _paginated_cfg(2)
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=[_products(4), _products(2)]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert not any("max_pages" in m for m in warnings), warnings


def test_run_site_no_undercount_warning_when_pagination_is_none(conn, caplog):
    cfg = _cfg()  # pagination type "none"
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(2)):
        run_site(cfg, conn)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert not any("max_pages" in m for m in warnings), warnings


def test_run_site_undercount_warning_does_not_mark_failure(conn, caplog):
    cfg = _paginated_cfg(2)
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=_products(2)), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0
    assert site["last_error"] is None


# ── run_site: multiple source_urls under one site ────────────────────────────

def _named_products(*names):
    return [
        {"raw_name": n, "price": 9.99, "availability": "in_stock", "product_url": "/p"}
        for n in names
    ]


def _run_with_pages(cfg, products_by_url, conn):
    """Run run_site serving one product list per URL.

    The stub fetch hands the URL back as the page body so the stub scraper can
    look that page's products up by it. Returns the URLs fetched, in order, and
    the patched sleep.
    """
    fetched = []

    def fake_fetch(url, **kwargs):
        fetched.append(url)
        return url

    def fake_scrape(html, config, from_preorder_url=False):
        return products_by_url.get(html, [])

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=fake_scrape), \
         patch("scraper.runner.time.sleep") as mock_sleep:
        run_site(cfg, conn)

    return fetched, mock_sleep


def _paged_cfg(urls, max_pages=2):
    cfg = _cfg(source_urls=urls)
    cfg["pagination"] = {
        "type": "url_pattern",
        "url_pattern": "?page={page}",
        "max_pages": max_pages,
    }
    return cfg


def test_run_site_source_urls_scrapes_every_url(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    fetched, _ = _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1", "A2"),
        "https://example.fi/b": _named_products("B1"),
    }, conn)

    assert fetched == ["https://example.fi/a", "https://example.fi/b"]
    names = [r["raw_name"] for r in conn.execute(
        "SELECT raw_name FROM listings ORDER BY raw_name")]
    assert names == ["A1", "A2", "B1"]


def test_run_site_source_urls_share_one_site_row(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1"),
        "https://example.fi/b": _named_products("B1"),
    }, conn)

    sites = conn.execute("SELECT id, url, name FROM sites").fetchall()
    assert len(sites) == 1
    assert sites[0]["url"] == "https://example.fi/a"  # first URL identifies the site
    site_ids = {r["site_id"] for r in conn.execute("SELECT site_id FROM listings")}
    assert site_ids == {sites[0]["id"]}


def test_run_site_source_urls_paginate_each_url_independently(conn):
    cfg = _paged_cfg(["https://example.fi/a", "https://example.fi/b"])
    fetched, _ = _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1", "A2"),
        "https://example.fi/a?page=2": _named_products("A3"),
        "https://example.fi/b": _named_products("B1", "B2"),
        "https://example.fi/b?page=2": _named_products("B3"),
    }, conn)

    assert fetched == [
        "https://example.fi/a",
        "https://example.fi/a?page=2",
        "https://example.fi/b",
        "https://example.fi/b?page=2",
    ]
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 6


def test_run_site_source_urls_empty_page_only_stops_that_url(conn):
    cfg = _paged_cfg(["https://example.fi/a", "https://example.fi/b"])
    fetched, _ = _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1"),
        "https://example.fi/a?page=2": [],
        "https://example.fi/b": _named_products("B1"),
        "https://example.fi/b?page=2": _named_products("B2"),
    }, conn)

    assert fetched == [
        "https://example.fi/a",
        "https://example.fi/a?page=2",
        "https://example.fi/b",
        "https://example.fi/b?page=2",
    ]
    names = [r["raw_name"] for r in conn.execute(
        "SELECT raw_name FROM listings ORDER BY raw_name")]
    assert names == ["A1", "B1", "B2"]


def test_run_site_source_urls_currency_per_url(conn):
    cfg = _cfg(source_urls=["https://example.se/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.se/a": _named_products("SE1"),
        "https://example.fi/b": _named_products("FI1"),
    }, conn)

    currencies = {r["raw_name"]: r["latest_currency"] for r in conn.execute(
        "SELECT raw_name, latest_currency FROM listings")}
    assert currencies == {"SE1": "SEK", "FI1": "EUR"}


def test_run_site_source_urls_product_url_resolved_against_its_own_url(conn):
    cfg = _cfg(source_urls=["https://example.fi/shop/a/", "https://other.fi/shop/b/"])
    _run_with_pages(cfg, {
        "https://example.fi/shop/a/": _named_products("A1"),
        "https://other.fi/shop/b/": _named_products("B1"),
    }, conn)

    urls = {r["raw_name"]: r["product_url"] for r in conn.execute(
        "SELECT raw_name, product_url FROM listings")}
    assert urls == {"A1": "https://example.fi/p", "B1": "https://other.fi/p"}


def test_run_site_source_urls_sleep_between_urls(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    _, mock_sleep = _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1"),
        "https://example.fi/b": _named_products("B1"),
    }, conn)

    assert mock_sleep.call_count == 1  # between the two URLs, not before the first


def test_run_site_source_urls_duplicate_raw_name_upserts_one_listing(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("Shared Box"),
        "https://example.fi/b": _named_products("Shared Box"),
    }, conn)

    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1

    # A second run with a lower price on both URLs: one price_drop, not two
    _run_with_pages(cfg, {
        "https://example.fi/a": [{**_named_products("Shared Box")[0], "price": 5.0}],
        "https://example.fi/b": [{**_named_products("Shared Box")[0], "price": 5.0}],
    }, conn)
    assert _event_types(conn) == ["price_drop"]


def test_run_site_source_urls_health_success_when_any_url_yields_products(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.fi/a": [],
        "https://example.fi/b": _named_products("B1"),
    }, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0
    assert site["last_error"] is None


def test_run_site_source_urls_fetch_failure_marks_site_failure(conn):
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])

    def fake_fetch(url, **kwargs):
        if url.endswith("/b"):
            raise FetchError("HTTP 500")
        return url

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=lambda html, cfg_, **kw: _named_products("A1")), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "500" in (site["last_error"] or "")
    # the first URL's sighting still persisted
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1


def test_run_site_page_failure_still_emits_the_earlier_pages_events(conn):
    """A 500 on page 2 must not swallow page 1's events. Page 1's listings are
    already committed, so the next run would diff against them and never report
    the drop. Most configs are single-URL, so this is the common shape of it."""
    cfg = _paged_cfg(["https://example.fi/a"])
    _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1"),
        "https://example.fi/a?page=2": _named_products("A2"),
    }, conn)
    assert _event_types(conn) == []  # first run is silent

    def fake_fetch(url, **kwargs):
        if url.endswith("?page=2"):
            raise FetchError("HTTP 500 for " + url, 500)
        return url

    def fake_scrape(html, cfg_, **kw):
        return [{**_named_products("A1")[0], "price": 4.99}]

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=fake_scrape), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "price_drop"
    assert rows[0]["raw_name"] == "A1"

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1


def test_run_site_source_urls_failure_still_emits_the_earlier_urls_events(conn):
    """The listings of a URL that succeeded are already committed, so their events
    must be written too. Dropping them means the next run diffs against the
    updated rows and the price drop is lost for good."""
    cfg = _cfg(source_urls=["https://example.fi/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1"),
        "https://example.fi/b": _named_products("B1"),
    }, conn)
    assert _event_types(conn) == []  # first run is silent

    def fake_fetch(url, **kwargs):
        if url.endswith("/b"):
            raise FetchError("HTTP 500")
        return url

    def fake_scrape(html, cfg_, **kw):
        return [{**_named_products("A1")[0], "price": 4.99}]

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=fake_scrape), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    rows = conn.execute("SELECT * FROM updates").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "price_drop"
    assert rows[0]["raw_name"] == "A1"
    assert rows[0]["new_value"] == "4.99"

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "500" in (site["last_error"] or "")


def test_run_site_source_urls_undercount_warning_names_the_url(conn, caplog):
    cfg = _paged_cfg(["https://example.fi/a", "https://example.fi/b"])
    _run_with_pages(cfg, {
        "https://example.fi/a": _named_products("A1", "A2"),
        "https://example.fi/a?page=2": _named_products("A3", "A4"),
        "https://example.fi/b": _named_products("B1", "B2"),
        "https://example.fi/b?page=2": _named_products("B3"),
    }, conn)

    undercount = [r.getMessage() for r in caplog.records if "max_pages" in r.getMessage()]
    assert len(undercount) == 1
    assert "https://example.fi/a" in undercount[0]


def test_run_site_404_on_later_page_ends_pagination_not_the_site(conn):
    """A 404 past page 1 is how WooCommerce says "no more pages"."""
    cfg = _paged_cfg(["https://example.fi/a"])

    def fake_fetch(url, **kwargs):
        if url.endswith("?page=2"):
            raise FetchError("HTTP 404 for " + url, 404)
        return url

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=lambda html, cfg_, **kw: _named_products("A1")), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0
    assert site["last_error"] is None
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1


def test_run_site_404_on_first_page_still_fails_the_url(conn):
    """A 404 on the entry URL itself is a real error, not an end-of-listing."""
    cfg = _paged_cfg(["https://example.fi/a"])

    with patch("scraper.runner.fetch", side_effect=FetchError("HTTP 404 for https://example.fi/a", 404)), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "404" in (site["last_error"] or "")


def test_run_site_404_on_later_page_keeps_other_source_urls(conn):
    """TCG-kauppa's regression: one short category must not void the whole site."""
    cfg = _paged_cfg(["https://example.fi/a", "https://example.fi/b"])

    def fake_fetch(url, **kwargs):
        if url == "https://example.fi/a?page=2":
            raise FetchError("HTTP 404 for " + url, 404)
        return url

    def fake_scrape(html, cfg_, **kw):
        return _named_products("B1") if "/b" in html else _named_products("A1")

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=fake_scrape), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 0
    names = sorted(r[0] for r in conn.execute("SELECT raw_name FROM listings"))
    assert names == ["A1", "B1"]


# ── run_site: preorder URLs ───────────────────────────────────────────────────

def _flag_by_name(conn) -> dict:
    return {r["raw_name"]: r["from_preorder_url"] for r in conn.execute(
        "SELECT raw_name, from_preorder_url FROM listings")}


def test_run_site_scrapes_preorder_urls_too(conn):
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakkotilaus/"]})
    fetched, _ = _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("A1"),
        "https://example.fi/ennakkotilaus/": _named_products("P1"),
    }, conn)

    assert fetched == ["https://example.fi/shop/", "https://example.fi/ennakkotilaus/"]
    assert _flag_by_name(conn) == {"A1": 0, "P1": 1}


def test_run_site_preorder_urls_share_the_site_identity(conn):
    """The site row keeps its first normal URL, not a preorder one."""
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakkotilaus/"]})
    _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("A1"),
        "https://example.fi/ennakkotilaus/": _named_products("P1"),
    }, conn)

    sites = conn.execute("SELECT id, url FROM sites").fetchall()
    assert len(sites) == 1
    assert sites[0]["url"] == "https://example.fi/shop/"


def test_run_site_preorder_urls_paginate_like_the_others(conn):
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakko"]})
    cfg["pagination"] = {"type": "url_pattern", "url_pattern": "?page={page}",
                         "max_pages": 2}
    fetched, _ = _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("A1", "A2"),
        "https://example.fi/shop/?page=2": _named_products("A3"),
        "https://example.fi/ennakko": _named_products("P1", "P2"),
        "https://example.fi/ennakko?page=2": _named_products("P3"),
    }, conn)

    assert fetched == ["https://example.fi/shop/", "https://example.fi/shop/?page=2",
                       "https://example.fi/ennakko", "https://example.fi/ennakko?page=2"]
    assert _flag_by_name(conn) == {"A1": 0, "A2": 0, "A3": 0, "P1": 1, "P2": 1, "P3": 1}


def test_run_site_reads_a_preorder_url_page_as_preorder(conn):
    """The whole chain, real parser included: badge says in stock, page says preorder."""
    def page(name):
        return (f"<ul><li class='product'><h2>{name}</h2>"
                f"<span class='badge'>In stock</span>"
                f"<span class='price'>9,99 €</span><a href='/p'>x</a></li></ul>")

    cfg = _cfg(extra={
        "preorder_urls": ["https://example.fi/ennakkotilaus/"],
        "availability": {"selector": ".badge",
                         "text_map": {"In stock": "in_stock"},
                         "default": "unknown"},
    })
    pages = {"https://example.fi/shop/": page("Normal Box"),
             "https://example.fi/ennakkotilaus/": page("Preorder Box")}

    with patch("scraper.runner.fetch", side_effect=lambda url, **kw: pages[url]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    rows = {r["raw_name"]: (r["availability"], r["availability_text"],
                            r["from_preorder_url"])
            for r in conn.execute("SELECT * FROM listings")}
    assert rows == {"Normal Box": ("in_stock", "In stock", 0),
                    "Preorder Box": ("preorder", "(preorder url)", 1)}


def test_run_site_listing_on_both_urls_keeps_the_last_sighting_flag(conn):
    """Preorder URLs come last, so a shared listing reads as a preorder."""
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakkotilaus/"]})
    _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("Shared Box"),
        "https://example.fi/ennakkotilaus/": _named_products("Shared Box"),
    }, conn)

    assert _flag_by_name(conn) == {"Shared Box": 1}


def test_run_site_dropping_a_listing_off_the_preorder_url_clears_the_flag(conn):
    """The flag means "seen on a preorder URL last run", not "ever seen on one"."""
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakkotilaus/"]})
    _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("Box"),
        "https://example.fi/ennakkotilaus/": _named_products("Box"),
    }, conn)
    assert _flag_by_name(conn) == {"Box": 1}

    _run_with_pages(cfg, {
        "https://example.fi/shop/": _named_products("Box"),
        "https://example.fi/ennakkotilaus/": [],
    }, conn)
    assert _flag_by_name(conn) == {"Box": 0}


def test_run_site_preorder_url_failure_marks_the_site_unhealthy(conn):
    cfg = _cfg(extra={"preorder_urls": ["https://example.fi/ennakkotilaus/"]})

    def fake_fetch(url, **kwargs):
        if "ennakkotilaus" in url:
            raise FetchError("HTTP 500 for " + url, 500)
        return url

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page",
               side_effect=lambda html, cfg_, **kw: _named_products("A1")), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "500" in (site["last_error"] or "")


def test_run_site_non_404_error_on_later_page_still_fails(conn):
    """A 500 mid-pagination is a real failure, not an end-of-listing signal."""
    cfg = _paged_cfg(["https://example.fi/a"])

    def fake_fetch(url, **kwargs):
        if url.endswith("?page=2"):
            raise FetchError("HTTP 500 for " + url, 500)
        return url

    with patch("scraper.runner.fetch", side_effect=fake_fetch), \
         patch("scraper.runner.scrape_page", side_effect=lambda html, cfg_, **kw: _named_products("A1")), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    site = conn.execute("SELECT * FROM sites WHERE name='Test Shop'").fetchone()
    assert site["consecutive_failures"] == 1
    assert "500" in (site["last_error"] or "")
