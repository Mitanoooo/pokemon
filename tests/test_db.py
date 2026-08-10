import sqlite3
import pytest
from pathlib import Path
from scraper import db

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    # Use get_connection so the fixture exercises the same factory the runtime uses.
    # In-memory DB can't use the file-path helper, so we wire row_factory manually
    # the same way get_connection does.
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    # seed one site row so FK constraints are satisfiable
    c.execute("INSERT INTO sites (url, name) VALUES ('https://example.fi', 'Example')")
    c.commit()
    return c


@pytest.fixture
def site_id(conn):
    row = conn.execute("SELECT id FROM sites WHERE url='https://example.fi'").fetchone()
    return row["id"]


# ── seam 1: write_readings with no alias → product_id is NULL ──────────────

def test_write_readings_no_alias_product_id_is_null(conn, site_id):
    readings = [
        {"raw_name": "Scarlet & Violet Booster Box", "price": 129.90, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    db.write_readings(conn, site_id, readings)

    row = conn.execute("SELECT product_id FROM price_readings").fetchone()
    assert row["product_id"] is None


# ── seam 2: write_readings after alias exists → product_id is populated ────

def test_write_readings_with_alias_product_id_is_set(conn, site_id):
    product_id = db.upsert_product(conn, "Scarlet & Violet Booster Box")
    db.upsert_alias(conn, "Scarlet & Violet Booster Box", site_id, product_id)

    readings = [
        {"raw_name": "Scarlet & Violet Booster Box", "price": 129.90, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    db.write_readings(conn, site_id, readings)

    row = conn.execute("SELECT product_id FROM price_readings").fetchone()
    assert row["product_id"] == product_id


# ── seam 3: get_products_below_threshold ────────────────────────────────────

def test_get_products_below_threshold_returns_matching_rows(conn, site_id):
    product_id = db.upsert_product(conn, "Prismatic Evolutions ETB")
    db.upsert_alias(conn, "Prismatic Evolutions ETB", site_id, product_id)
    conn.execute(
        "INSERT INTO thresholds (product_id, price, active) VALUES (?, ?, 1)",
        (product_id, 50.00),
    )
    conn.commit()

    readings = [{"raw_name": "Prismatic Evolutions ETB", "price": 44.90, "currency": "EUR", "in_stock": True, "product_url": "https://example.fi/etb"}]
    db.write_readings(conn, site_id, readings)

    rows = db.get_products_below_threshold(conn)
    assert len(rows) == 1
    assert rows[0]["canonical_name"] == "Prismatic Evolutions ETB"
    assert rows[0]["price"] == 44.90


def test_get_products_below_threshold_omits_rows_above_threshold(conn, site_id):
    product_id = db.upsert_product(conn, "Prismatic Evolutions ETB")
    db.upsert_alias(conn, "Prismatic Evolutions ETB", site_id, product_id)
    conn.execute(
        "INSERT INTO thresholds (product_id, price, active) VALUES (?, ?, 1)",
        (product_id, 50.00),
    )
    conn.commit()

    readings = [{"raw_name": "Prismatic Evolutions ETB", "price": 59.90, "currency": "EUR", "in_stock": True, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    rows = db.get_products_below_threshold(conn)
    assert rows == []


def test_get_products_below_threshold_omits_inactive_thresholds(conn, site_id):
    product_id = db.upsert_product(conn, "Prismatic Evolutions ETB")
    db.upsert_alias(conn, "Prismatic Evolutions ETB", site_id, product_id)
    conn.execute(
        "INSERT INTO thresholds (product_id, price, active) VALUES (?, ?, 0)",
        (product_id, 50.00),
    )
    conn.commit()

    readings = [{"raw_name": "Prismatic Evolutions ETB", "price": 44.90, "currency": "EUR", "in_stock": True, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    rows = db.get_products_below_threshold(conn)
    assert rows == []


# ── get_unmapped_raw_names ───────────────────────────────────────────────────

def test_get_unmapped_raw_names_returns_names_with_no_alias(conn, site_id):
    readings = [{"raw_name": "Mystery Set Booster", "price": 19.90, "currency": "EUR", "in_stock": None, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    names = db.get_unmapped_raw_names(conn)
    assert any(r["raw_name"] == "Mystery Set Booster" for r in names)


def test_get_unmapped_raw_names_excludes_mapped_names(conn, site_id):
    product_id = db.upsert_product(conn, "Mystery Set Booster")
    db.upsert_alias(conn, "Mystery Set Booster", site_id, product_id)

    readings = [{"raw_name": "Mystery Set Booster", "price": 19.90, "currency": "EUR", "in_stock": None, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    names = db.get_unmapped_raw_names(conn)
    assert names == []


# ── update_site_health ───────────────────────────────────────────────────────

def test_update_site_health_success_resets_failures(conn, site_id):
    conn.execute("UPDATE sites SET consecutive_failures=3 WHERE id=?", (site_id,))
    conn.commit()

    db.update_site_health(conn, site_id, success=True)

    row = conn.execute("SELECT consecutive_failures, last_error FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["consecutive_failures"] == 0
    assert row["last_error"] is None


def test_update_site_health_failure_increments_failures(conn, site_id):
    db.update_site_health(conn, site_id, success=False, error_text="0 products found")
    db.update_site_health(conn, site_id, success=False, error_text="0 products found")

    row = conn.execute("SELECT consecutive_failures, last_error FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["consecutive_failures"] == 2
    assert row["last_error"] == "0 products found"


# ── currency stored per reading ─────────────────────────────────────────────

def test_write_readings_stores_currency_per_row(conn, site_id):
    readings = [{"raw_name": "Booster Pack", "price": 5499.0, "currency": "SEK", "in_stock": True, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    row = conn.execute("SELECT currency FROM price_readings").fetchone()
    assert row["currency"] == "SEK"


# ── update_site_health: null_price_count ────────────────────────────────────

def test_update_site_health_persists_null_price_count(conn, site_id):
    db.update_site_health(conn, site_id, success=True, null_price_count=3)
    row = conn.execute("SELECT null_price_count FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["null_price_count"] == 3


def test_update_site_health_null_price_count_zero_on_clean_run(conn, site_id):
    db.update_site_health(conn, site_id, success=True, null_price_count=5)
    db.update_site_health(conn, site_id, success=True, null_price_count=0)
    row = conn.execute("SELECT null_price_count FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["null_price_count"] == 0


# ── upsert_alias remap ────────────────────────────────────────────────────────

def test_upsert_alias_remap_updates_product_id(conn, site_id):
    product_a = db.upsert_product(conn, "Wrong Product")
    product_b = db.upsert_product(conn, "Correct Product")

    db.upsert_alias(conn, "Some Raw Name", site_id, product_a)
    db.upsert_alias(conn, "Some Raw Name", site_id, product_b)  # correction

    row = conn.execute(
        "SELECT product_id FROM product_aliases WHERE raw_name='Some Raw Name' AND site_id=?",
        (site_id,),
    ).fetchone()
    assert row["product_id"] == product_b
