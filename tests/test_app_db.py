"""Tests for the db query helpers used by the Streamlit pages."""
import sqlite3
import pytest
from pathlib import Path
from scraper import db

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute("INSERT INTO sites (url, name) VALUES ('https://a.fi', 'SiteA')")
    c.execute("INSERT INTO sites (url, name) VALUES ('https://b.fi', 'SiteB')")
    c.commit()
    return c


@pytest.fixture
def site_a(conn):
    return conn.execute("SELECT id FROM sites WHERE url='https://a.fi'").fetchone()["id"]


@pytest.fixture
def site_b(conn):
    return conn.execute("SELECT id FROM sites WHERE url='https://b.fi'").fetchone()["id"]


# ── get_site_health ──────────────────────────────────────────────────────────

def test_get_site_health_returns_all_sites(conn):
    rows = db.get_site_health(conn)
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"SiteA", "SiteB"}


def test_get_site_health_broken_sites_first(conn, site_a, site_b):
    conn.execute("UPDATE sites SET consecutive_failures=3 WHERE id=?", (site_a,))
    conn.commit()

    rows = db.get_site_health(conn)
    assert rows[0]["name"] == "SiteA"
    assert rows[0]["consecutive_failures"] == 3


def test_get_site_health_empty_db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    assert db.get_site_health(c) == []


# ── get_products_summary ─────────────────────────────────────────────────────

def test_get_products_summary_empty_returns_empty(conn):
    assert db.get_products_summary(conn) == []


def test_get_products_summary_no_readings(conn):
    db.upsert_product(conn, "Booster Box")
    rows = db.get_products_summary(conn)
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "Booster Box"
    assert rows[0]["lowest_price"] is None
    assert rows[0]["category"] == "Uncategorised"


def test_get_products_summary_with_readings(conn, site_a, site_b):
    pid = db.upsert_product(conn, "Scarlet Violet Box")
    db.upsert_alias(conn, "Scarlet Violet Box", site_a, pid)
    db.upsert_alias(conn, "SV Box", site_b, pid)
    db.write_readings(conn, site_a, [{"raw_name": "Scarlet Violet Box", "price": 120.0, "currency": "EUR", "in_stock": True, "product_url": ""}])
    db.write_readings(conn, site_b, [{"raw_name": "SV Box", "price": 110.0, "currency": "EUR", "in_stock": True, "product_url": ""}])

    rows = db.get_products_summary(conn)
    assert len(rows) == 1
    r = rows[0]
    assert r["lowest_price"] == 110.0
    assert r["cheapest_site"] == "SiteB"
    assert r["sites_in_stock"] == 2


def test_get_products_summary_sites_in_stock_excludes_out_of_stock(conn, site_a, site_b):
    pid = db.upsert_product(conn, "Stock Test Product")
    db.upsert_alias(conn, "Stock Test Product", site_a, pid)
    db.upsert_alias(conn, "STP", site_b, pid)
    db.write_readings(conn, site_a, [{"raw_name": "Stock Test Product", "price": 100.0, "currency": "EUR", "in_stock": True, "product_url": ""}])
    db.write_readings(conn, site_b, [{"raw_name": "STP", "price": 90.0, "currency": "EUR", "in_stock": False, "product_url": ""}])

    rows = db.get_products_summary(conn)
    assert rows[0]["sites_in_stock"] == 1


def test_get_products_summary_category_assigned(conn, site_a):
    conn.execute("INSERT INTO categories (name) VALUES ('Booster Boxes')")
    conn.commit()
    cat_id = conn.execute("SELECT id FROM categories WHERE name='Booster Boxes'").fetchone()["id"]

    conn.execute("INSERT INTO products (canonical_name, category_id) VALUES (?, ?)", ("Champion ETB", cat_id))
    conn.commit()

    rows = db.get_products_summary(conn)
    assert rows[0]["category"] == "Booster Boxes"


def test_get_products_summary_uncategorised_last(conn):
    conn.execute("INSERT INTO categories (name) VALUES ('Alpha')")
    conn.commit()
    cat_id = conn.execute("SELECT id FROM categories WHERE name='Alpha'").fetchone()["id"]

    conn.execute("INSERT INTO products (canonical_name, category_id) VALUES ('Cat Product', ?)", (cat_id,))
    conn.execute("INSERT INTO products (canonical_name) VALUES ('Uncat Product')")
    conn.commit()

    rows = db.get_products_summary(conn)
    categories = [r["category"] for r in rows]
    assert categories.index("Alpha") < categories.index("Uncategorised")


# ── get_product_price_history ────────────────────────────────────────────────

def test_get_product_price_history_empty(conn):
    pid = db.upsert_product(conn, "No Data Product")
    assert db.get_product_price_history(conn, pid) == []


def test_get_product_price_history_multiple_sites(conn, site_a, site_b):
    pid = db.upsert_product(conn, "Multi Site Product")
    db.upsert_alias(conn, "Multi Site Product", site_a, pid)
    db.upsert_alias(conn, "MSP", site_b, pid)
    db.write_readings(conn, site_a, [{"raw_name": "Multi Site Product", "price": 100.0, "currency": "EUR", "in_stock": True, "product_url": ""}])
    db.write_readings(conn, site_b, [{"raw_name": "MSP", "price": 95.0, "currency": "EUR", "in_stock": True, "product_url": ""}])

    rows = db.get_product_price_history(conn, pid)
    assert len(rows) == 2
    site_names = {r["site_name"] for r in rows}
    assert site_names == {"SiteA", "SiteB"}
    assert all(r["price"] > 0 for r in rows)


def test_get_product_price_history_ordered_by_time(conn, site_a):
    pid = db.upsert_product(conn, "Time Product")
    db.upsert_alias(conn, "Time Product", site_a, pid)
    # Insert two readings with explicit timestamps
    conn.execute(
        "INSERT INTO price_readings (product_id, site_id, raw_name, price, currency, in_stock, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (pid, site_a, "Time Product", 50.0, "EUR", 1, "2026-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO price_readings (product_id, site_id, raw_name, price, currency, in_stock, scraped_at) VALUES (?,?,?,?,?,?,?)",
        (pid, site_a, "Time Product", 45.0, "EUR", 1, "2026-01-02 00:00:00"),
    )
    conn.commit()

    rows = db.get_product_price_history(conn, pid)
    assert rows[0]["scraped_at"] < rows[1]["scraped_at"]
    assert rows[0]["price"] == 50.0
    assert rows[1]["price"] == 45.0


def test_get_product_price_history_sek_currency(conn, site_a):
    pid = db.upsert_product(conn, "SEK Product")
    db.upsert_alias(conn, "SEK Product", site_a, pid)
    db.write_readings(conn, site_a, [{"raw_name": "SEK Product", "price": 1299.0, "currency": "SEK", "in_stock": True, "product_url": ""}])

    rows = db.get_product_price_history(conn, pid)
    assert rows[0]["currency"] == "SEK"
