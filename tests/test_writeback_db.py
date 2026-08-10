"""Tests for write-back db helpers used by Unknowns, Categories, Thresholds pages."""
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


def _add_category(conn, name):
    conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()["id"]


# ── get_all_categories ────────────────────────────────────────────────────────

def test_get_all_categories_empty(conn):
    assert db.get_all_categories(conn) == []


def test_get_all_categories_returns_sorted(conn):
    _add_category(conn, "Zeta")
    _add_category(conn, "Alpha")
    rows = db.get_all_categories(conn)
    names = [r["name"] for r in rows]
    assert names == ["Alpha", "Zeta"]


# ── add_category ──────────────────────────────────────────────────────────────

def test_add_category_inserts_row(conn):
    db.add_category(conn, "ETBs")
    rows = db.get_all_categories(conn)
    assert any(r["name"] == "ETBs" for r in rows)


def test_add_category_returns_id(conn):
    cat_id = db.add_category(conn, "ETBs")
    assert isinstance(cat_id, int)
    assert cat_id > 0


# ── rename_category ───────────────────────────────────────────────────────────

def test_rename_category_updates_name(conn):
    cat_id = _add_category(conn, "Old Name")
    db.rename_category(conn, cat_id, "New Name")
    rows = db.get_all_categories(conn)
    names = [r["name"] for r in rows]
    assert "New Name" in names
    assert "Old Name" not in names


def test_rename_category_does_not_create_duplicate(conn):
    cat_id = _add_category(conn, "Original")
    db.rename_category(conn, cat_id, "Renamed")
    rows = db.get_all_categories(conn)
    assert len(rows) == 1


# ── get_all_canonical_products ────────────────────────────────────────────────

def test_get_all_canonical_products_empty(conn):
    assert db.get_all_canonical_products(conn) == []


def test_get_all_canonical_products_returns_named_only(conn):
    db.upsert_product(conn, "Named Product")
    conn.execute("INSERT INTO products (canonical_name) VALUES (NULL)")
    conn.commit()
    rows = db.get_all_canonical_products(conn)
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "Named Product"


def test_get_all_canonical_products_sorted_by_name(conn):
    db.upsert_product(conn, "Zeta Box")
    db.upsert_product(conn, "Alpha ETB")
    rows = db.get_all_canonical_products(conn)
    names = [r["canonical_name"] for r in rows]
    assert names == ["Alpha ETB", "Zeta Box"]


# ── set_product_category ──────────────────────────────────────────────────────

def test_set_product_category_assigns_category(conn):
    pid = db.upsert_product(conn, "Test Product")
    cat_id = _add_category(conn, "Boxes")
    db.set_product_category(conn, pid, cat_id)
    row = conn.execute("SELECT category_id FROM products WHERE id=?", (pid,)).fetchone()
    assert row["category_id"] == cat_id


def test_set_product_category_clears_to_none(conn):
    pid = db.upsert_product(conn, "Test Product")
    cat_id = _add_category(conn, "Boxes")
    db.set_product_category(conn, pid, cat_id)
    db.set_product_category(conn, pid, None)
    row = conn.execute("SELECT category_id FROM products WHERE id=?", (pid,)).fetchone()
    assert row["category_id"] is None


# ── get_thresholds_for_all_products ──────────────────────────────────────────

def test_get_thresholds_empty(conn):
    assert db.get_thresholds_for_all_products(conn) == []


def test_get_thresholds_no_threshold_row(conn):
    db.upsert_product(conn, "No Threshold")
    rows = db.get_thresholds_for_all_products(conn)
    assert len(rows) == 1
    assert rows[0]["threshold_price"] is None
    assert rows[0]["lowest_price"] is None


def test_get_thresholds_with_readings(conn, site_a):
    pid = db.upsert_product(conn, "Priced Product")
    db.upsert_alias(conn, "Priced Product", site_a, pid)
    db.write_readings(conn, site_a, [{"raw_name": "Priced Product", "price": 99.9, "currency": "EUR", "in_stock": True, "product_url": ""}])
    rows = db.get_thresholds_for_all_products(conn)
    assert rows[0]["lowest_price"] == 99.9
    assert rows[0]["currency"] == "EUR"


def test_get_thresholds_currency_matches_cheapest_site(conn, site_a):
    """Currency field must come from the cheapest site, not an arbitrary row."""
    site_b = conn.execute("SELECT id FROM sites WHERE url='https://b.fi'").fetchone()["id"]
    pid = db.upsert_product(conn, "Multi-currency Product")
    db.upsert_alias(conn, "MCP", site_a, pid)
    db.upsert_alias(conn, "MCP2", site_b, pid)
    # site_a is cheaper but uses SEK; site_b is more expensive but uses EUR
    db.write_readings(conn, site_a, [{"raw_name": "MCP", "price": 50.0, "currency": "SEK", "in_stock": True, "product_url": ""}])
    db.write_readings(conn, site_b, [{"raw_name": "MCP2", "price": 80.0, "currency": "EUR", "in_stock": True, "product_url": ""}])
    rows = db.get_thresholds_for_all_products(conn)
    assert rows[0]["lowest_price"] == 50.0
    assert rows[0]["currency"] == "SEK"


def test_get_thresholds_excludes_null_canonical_name(conn):
    conn.execute("INSERT INTO products (canonical_name) VALUES (NULL)")
    conn.commit()
    assert db.get_thresholds_for_all_products(conn) == []


# ── save_threshold ────────────────────────────────────────────────────────────

def test_save_threshold_creates_row(conn):
    pid = db.upsert_product(conn, "New Product")
    db.save_threshold(conn, pid, 50.0, True)
    row = conn.execute(
        "SELECT price, active FROM thresholds WHERE product_id=?", (pid,)
    ).fetchone()
    assert row["price"] == 50.0
    assert row["active"] == 1


def test_save_threshold_updates_existing_row(conn):
    pid = db.upsert_product(conn, "Existing Product")
    db.save_threshold(conn, pid, 50.0, True)
    db.save_threshold(conn, pid, 40.0, True)
    rows = conn.execute(
        "SELECT price FROM thresholds WHERE product_id=?", (pid,)
    ).fetchall()
    # Only one row should exist
    assert len(rows) == 1
    assert rows[0]["price"] == 40.0


def test_save_threshold_deactivate_sets_active_zero(conn):
    pid = db.upsert_product(conn, "Deactivate Product")
    db.save_threshold(conn, pid, 50.0, True)
    db.save_threshold(conn, pid, 50.0, False)
    row = conn.execute(
        "SELECT active FROM thresholds WHERE product_id=?", (pid,)
    ).fetchone()
    assert row["active"] == 0


def test_save_threshold_deactivated_excluded_from_digest(conn, site_a):
    pid = db.upsert_product(conn, "Digest Product")
    db.upsert_alias(conn, "Digest Product", site_a, pid)
    db.write_readings(conn, site_a, [{"raw_name": "Digest Product", "price": 30.0, "currency": "EUR", "in_stock": True, "product_url": ""}])
    db.save_threshold(conn, pid, 50.0, False)  # deactivated
    rows = db.get_products_below_threshold(conn)
    assert rows == []


def test_save_threshold_one_row_per_product(conn):
    pid = db.upsert_product(conn, "One Row")
    db.save_threshold(conn, pid, 100.0, True)
    db.save_threshold(conn, pid, 90.0, True)
    db.save_threshold(conn, pid, 80.0, False)
    count = conn.execute(
        "SELECT COUNT(*) FROM thresholds WHERE product_id=?", (pid,)
    ).fetchone()[0]
    assert count == 1
