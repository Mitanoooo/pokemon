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


# ── helpers ──────────────────────────────────────────────────────────────────

def _add_product(conn, name, product_id=None):
    """Insert a cardmarket_products row and return its id."""
    if product_id is None:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next FROM cardmarket_products").fetchone()
        product_id = row["next"]
    conn.execute(
        """
        INSERT INTO cardmarket_products (id, name, id_category, category_name, id_expansion)
        VALUES (?, ?, 1, 'Booster Boxes', 1)
        """,
        (product_id, name),
    )
    conn.commit()
    return product_id


def _map_name(conn, raw_name, product_id):
    """Insert a 'mapped' name_mappings row — the lookup write_readings uses."""
    conn.execute(
        """
        INSERT INTO name_mappings (raw_name, cardmarket_product_id, status, mapped_at)
        VALUES (?, ?, 'mapped', datetime('now'))
        """,
        (raw_name, product_id),
    )
    conn.commit()


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
    product_id = _add_product(conn, "Scarlet & Violet Booster Box")
    _map_name(conn, "Scarlet & Violet Booster Box", product_id)

    readings = [
        {"raw_name": "Scarlet & Violet Booster Box", "price": 129.90, "currency": "EUR", "in_stock": True, "product_url": ""},
    ]
    db.write_readings(conn, site_id, readings)

    row = conn.execute("SELECT product_id FROM price_readings").fetchone()
    assert row["product_id"] == product_id


# ── seam 3: get_products_below_threshold ────────────────────────────────────

def test_get_products_below_threshold_returns_matching_rows(conn, site_id):
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    _map_name(conn, "Prismatic Evolutions ETB", product_id)
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
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    _map_name(conn, "Prismatic Evolutions ETB", product_id)
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
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    _map_name(conn, "Prismatic Evolutions ETB", product_id)
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
    product_id = _add_product(conn, "Mystery Set Booster")
    _map_name(conn, "Mystery Set Booster", product_id)

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


# ── save_mapping remap ────────────────────────────────────────────────────────

def test_save_mapping_remap_updates_product_id(conn, site_id):
    product_a = _add_product(conn, "Wrong Product")
    product_b = _add_product(conn, "Correct Product")

    _map_name(conn, "Some Raw Name", product_a)
    db.save_mapping(conn, "Some Raw Name", product_b)  # correction

    row = conn.execute(
        "SELECT cardmarket_product_id, status FROM name_mappings WHERE raw_name='Some Raw Name'"
    ).fetchone()
    assert row["cardmarket_product_id"] == product_b
    assert row["status"] == "mapped"


# ── scrape_runs ───────────────────────────────────────────────────────────────

def test_start_run_creates_row_with_started_at(conn):
    run_id = db.start_run(conn)

    row = conn.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["started_at"] is not None
    assert row["finished_at"] is None


def test_finish_run_stamps_finished_at(conn):
    run_id = db.start_run(conn)
    db.finish_run(conn, run_id)

    row = conn.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["finished_at"] is not None


def test_start_run_returns_distinct_ids(conn):
    assert db.start_run(conn) != db.start_run(conn)


# ── write_readings: run_id ────────────────────────────────────────────────────

def test_write_readings_stamps_run_id(conn, site_id):
    run_id = db.start_run(conn)
    readings = [{"raw_name": "Booster Box", "price": 99.90, "currency": "EUR", "in_stock": True, "product_url": ""}]
    db.write_readings(conn, site_id, readings, run_id=run_id)

    row = conn.execute("SELECT run_id FROM price_readings").fetchone()
    assert row["run_id"] == run_id


def test_write_readings_without_run_id_leaves_it_null(conn, site_id):
    readings = [{"raw_name": "Booster Box", "price": 99.90, "currency": "EUR", "in_stock": True, "product_url": ""}]
    db.write_readings(conn, site_id, readings)

    row = conn.execute("SELECT run_id FROM price_readings").fetchone()
    assert row["run_id"] is None


# ── upsert_listing ────────────────────────────────────────────────────────────

def test_upsert_listing_new_pair_sets_first_seen_equal_to_last_seen(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(
        conn, site_id, "Prismatic Evolutions ETB",
        product_url="https://example.fi/p/prismatic",
        price=54.90, currency="EUR", in_stock=True, run_id=run_id,
    )

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert row["first_seen_at"] == row["last_seen_at"]
    assert row["product_url"] == "https://example.fi/p/prismatic"
    assert row["latest_price"] == 54.90
    assert row["latest_currency"] == "EUR"
    assert row["latest_in_stock"] == 1
    assert row["last_run_id"] == run_id


def test_upsert_listing_known_pair_updates_last_seen_not_first_seen(conn, site_id):
    first_run = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      99.90, "EUR", True, first_run)

    # Backdate both timestamps so "first_seen_at unchanged, last_seen_at moved"
    # is observable — _now() has second resolution and both upserts land in the
    # same second otherwise.
    conn.execute("UPDATE listings SET first_seen_at = '2020-01-01 00:00:00', last_seen_at = '2020-01-01 00:00:00'")
    conn.commit()

    second_run = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      89.90, "EUR", True, second_run)

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
    assert row["first_seen_at"] == "2020-01-01 00:00:00"
    assert row["last_seen_at"] > "2020-01-01 00:00:00"
    assert row["latest_price"] == 89.90
    assert row["last_run_id"] == second_run


def test_upsert_listing_with_null_price_stores_null_latest_price(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Single Card", "https://example.fi/p/card",
                      None, "EUR", None, run_id)

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert row["latest_price"] is None
    assert row["raw_name"] == "Single Card"


def test_upsert_listing_null_price_does_not_erase_known_price(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      99.90, "EUR", True, run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      None, "EUR", True, run_id)

    row = conn.execute("SELECT latest_price FROM listings").fetchone()
    assert row["latest_price"] == 99.90


def test_upsert_listing_empty_url_does_not_erase_known_url(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      99.90, "EUR", True, run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", True, run_id)

    row = conn.execute("SELECT product_url FROM listings").fetchone()
    assert row["product_url"] == "https://example.fi/p/1"


def test_upsert_listing_resolves_product_id_from_name_mappings(conn, site_id):
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    _map_name(conn, "Prismatic ETB raw", product_id)

    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Prismatic ETB raw", "https://example.fi/p/1",
                      54.90, "EUR", True, run_id)

    row = conn.execute("SELECT product_id FROM listings").fetchone()
    assert row["product_id"] == product_id


def test_upsert_listing_unmapped_name_leaves_product_id_null(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Unknown Thing", "", 5.0, "EUR", None, run_id)

    row = conn.execute("SELECT product_id FROM listings").fetchone()
    assert row["product_id"] is None


# ── get_listing_state ─────────────────────────────────────────────────────────

def test_get_listing_state_returns_rows_keyed_by_raw_name(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box A", "https://example.fi/a", 10.0, "EUR", True, run_id)
    db.upsert_listing(conn, site_id, "Box B", "https://example.fi/b", 20.0, "EUR", False, run_id)

    state = db.get_listing_state(conn, site_id)
    assert set(state) == {"Box A", "Box B"}
    assert state["Box A"]["latest_price"] == 10.0
    assert state["Box B"]["latest_in_stock"] == 0


def test_get_listing_state_empty_for_unseen_site(conn, site_id):
    assert db.get_listing_state(conn, site_id) == {}


def test_get_listing_state_excludes_other_sites(conn, site_id):
    cur = conn.execute("INSERT INTO sites (url, name) VALUES ('https://other.fi', 'Other')")
    other_id = cur.lastrowid
    conn.commit()

    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Mine", "", 10.0, "EUR", True, run_id)
    db.upsert_listing(conn, other_id, "Theirs", "", 20.0, "EUR", True, run_id)

    assert set(db.get_listing_state(conn, site_id)) == {"Mine"}


# ── save_mapping backfills listings ───────────────────────────────────────────

def test_save_mapping_backfills_listings_product_id(conn, site_id):
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    conn.execute(
        "INSERT INTO name_mappings (raw_name, status) VALUES ('Prismatic ETB raw', 'undecided')"
    )
    conn.commit()

    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Prismatic ETB raw", "", 54.90, "EUR", True, run_id)
    assert conn.execute("SELECT product_id FROM listings").fetchone()["product_id"] is None

    db.save_mapping(conn, "Prismatic ETB raw", product_id)

    row = conn.execute("SELECT product_id FROM listings").fetchone()
    assert row["product_id"] == product_id


def test_save_mapping_backfills_listings_across_all_sites(conn, site_id):
    product_id = _add_product(conn, "Prismatic Evolutions ETB")
    cur = conn.execute("INSERT INTO sites (url, name) VALUES ('https://other.fi', 'Other')")
    other_id = cur.lastrowid
    conn.execute(
        "INSERT INTO name_mappings (raw_name, status) VALUES ('Prismatic ETB raw', 'undecided')"
    )
    conn.commit()

    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Prismatic ETB raw", "", 54.90, "EUR", True, run_id)
    db.upsert_listing(conn, other_id, "Prismatic ETB raw", "", 51.90, "EUR", True, run_id)

    db.save_mapping(conn, "Prismatic ETB raw", product_id)

    ids = [r["product_id"] for r in conn.execute("SELECT product_id FROM listings").fetchall()]
    assert ids == [product_id, product_id]


def test_save_mapping_null_mapped_leaves_listings_product_id_null(conn, site_id):
    conn.execute(
        "INSERT INTO name_mappings (raw_name, status) VALUES ('Some Sleeve', 'undecided')"
    )
    conn.commit()

    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Some Sleeve", "", 5.90, "EUR", True, run_id)
    db.save_mapping(conn, "Some Sleeve", None)

    row = conn.execute("SELECT product_id FROM listings").fetchone()
    assert row["product_id"] is None
    status = conn.execute(
        "SELECT status FROM name_mappings WHERE raw_name='Some Sleeve'"
    ).fetchone()["status"]
    assert status == "null_mapped"
