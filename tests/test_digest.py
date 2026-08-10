"""Tests for scraper.digest build_digest and send_digest."""
import sqlite3
from pathlib import Path

import pytest

from scraper import db
from scraper.digest import build_digest, send_digest

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _seed(conn, product_name, threshold, site_name, site_url, price, currency="EUR"):
    """Seed one (product, threshold, site, reading) chain."""
    c = conn
    c.execute("INSERT OR IGNORE INTO sites (url, name) VALUES (?, ?)", (site_url, site_name))
    site_id = c.execute("SELECT id FROM sites WHERE url=?", (site_url,)).fetchone()["id"]

    c.execute("INSERT OR IGNORE INTO products (canonical_name) VALUES (?)", (product_name,))
    product_id = c.execute("SELECT id FROM products WHERE canonical_name=?", (product_name,)).fetchone()["id"]

    # threshold
    c.execute("INSERT INTO thresholds (product_id, price, active) VALUES (?, ?, 1)", (product_id, threshold))

    # price reading
    c.execute(
        "INSERT INTO price_readings (product_id, site_id, raw_name, price, currency, scraped_at) "
        "VALUES (?, ?, ?, ?, ?, '2026-01-01 10:00:00')",
        (product_id, site_id, product_name, price, currency),
    )
    c.commit()
    return product_id, site_id


# ── build_digest ──────────────────────────────────────────────────────────────

def test_build_digest_returns_none_when_nothing_below_threshold(conn):
    _seed(conn, "Booster Box", 50.0, "Site A", "https://a.fi", price=60.0)
    assert build_digest(conn) is None


def test_build_digest_returns_html_when_rows_below_threshold(conn):
    _seed(conn, "Booster Box", 100.0, "Site A", "https://a.fi", price=79.0)
    result = build_digest(conn)
    assert result is not None
    html, n = result
    assert "Booster Box" in html
    assert "79" in html


def test_build_digest_n_products_is_distinct_product_count(conn):
    _seed(conn, "Booster Box", 100.0, "Site A", "https://a.fi", price=79.0)
    _seed(conn, "Booster Box", 100.0, "Site B", "https://b.fi", price=75.0)
    _seed(conn, "ETB", 80.0, "Site A", "https://a.fi", price=70.0)
    _, n = build_digest(conn)
    assert n == 2  # 2 distinct products, not 3 rows


def test_build_digest_shows_all_sites_below_threshold(conn):
    _seed(conn, "ETB", 80.0, "Site A", "https://a.fi", price=70.0)
    _seed(conn, "ETB", 80.0, "Site B", "https://b.fi", price=75.0)
    html, _ = build_digest(conn)
    assert "Site A" in html
    assert "Site B" in html


def test_build_digest_excludes_site_above_threshold(conn):
    _seed(conn, "ETB", 80.0, "Site A", "https://a.fi", price=70.0)
    _seed(conn, "ETB", 80.0, "Site B", "https://b.fi", price=90.0)
    html, _ = build_digest(conn)
    assert "Site A" in html
    assert "Site B" not in html


def test_build_digest_site_name_is_hyperlink(conn):
    _seed(conn, "Booster Box", 100.0, "My Shop", "https://myshop.fi", price=50.0)
    html, _ = build_digest(conn)
    assert '<a href="https://myshop.fi"' in html


def test_build_digest_shows_currency(conn):
    _seed(conn, "Booster Box", 100.0, "Spelparken", "https://spelparken.se", price=50.0, currency="SEK")
    html, _ = build_digest(conn)
    assert "SEK" in html


# ── send_digest (file transport) ──────────────────────────────────────────────

def test_send_digest_file_transport_writes_file(tmp_path):
    html = "<html><body>test</body></html>"
    out = tmp_path / "digest.html"
    send_digest(html, n_products=1, smtp_cfg=None, file_transport=str(out))
    assert out.exists()
    assert "test" in out.read_text()
