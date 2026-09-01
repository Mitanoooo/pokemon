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


def test_update_site_health_persists_null_price_count(conn, site_id):
    db.update_site_health(conn, site_id, success=True, null_price_count=3)
    row = conn.execute("SELECT null_price_count FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["null_price_count"] == 3


def test_update_site_health_null_price_count_zero_on_clean_run(conn, site_id):
    db.update_site_health(conn, site_id, success=True, null_price_count=5)
    db.update_site_health(conn, site_id, success=True, null_price_count=0)
    row = conn.execute("SELECT null_price_count FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["null_price_count"] == 0


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
    assert row["availability"] == "in_stock"
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


def test_upsert_listing_availability_is_overwritten_not_coalesced(conn, site_id):
    """availability means "state as of the last sighting", so a later unknown
    replaces a known state rather than being COALESCEd away."""
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", True, run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", None, run_id)

    row = conn.execute("SELECT availability FROM listings").fetchone()
    assert row["availability"] == "unknown"


def test_upsert_listing_out_of_stock_sighting_stored_as_out_of_stock(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", False, run_id)

    row = conn.execute("SELECT availability FROM listings").fetchone()
    assert row["availability"] == "out_of_stock"


# ── get_listing_state ─────────────────────────────────────────────────────────

def test_get_listing_state_returns_rows_keyed_by_raw_name(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box A", "https://example.fi/a", 10.0, "EUR", True, run_id)
    db.upsert_listing(conn, site_id, "Box B", "https://example.fi/b", 20.0, "EUR", False, run_id)

    state = db.get_listing_state(conn, site_id)
    assert set(state) == {"Box A", "Box B"}
    assert state["Box A"]["latest_price"] == 10.0
    assert state["Box B"]["availability"] == "out_of_stock"


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


# ── write_updates ─────────────────────────────────────────────────────────────

def test_write_updates_stores_correct_fields(conn, site_id):
    run_id = db.start_run(conn)
    events = [
        {"run_id": run_id, "site_id": site_id, "raw_name": "Box",
         "event_type": "new_listing", "old_value": None, "new_value": "9.99"},
    ]
    db.write_updates(conn, events)

    row = conn.execute("SELECT * FROM updates").fetchone()
    assert row["run_id"] == run_id
    assert row["site_id"] == site_id
    assert row["raw_name"] == "Box"
    assert row["event_type"] == "new_listing"
    assert row["new_value"] == "9.99"
    assert row["old_value"] is None
    assert row["seen"] == 0


# ── prune_updates ─────────────────────────────────────────────────────────────

def test_prune_updates_deletes_old_rows_leaves_recent(conn, site_id):
    run_id = db.start_run(conn)
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type, created_at) "
        "VALUES (?, ?, 'Old Box', 'new_listing', '2020-01-01 00:00:00')",
        (run_id, site_id),
    )
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) "
        "VALUES (?, ?, 'New Box', 'new_listing')",
        (run_id, site_id),
    )
    conn.commit()

    db.prune_updates(conn, days=30)

    names = [r["raw_name"] for r in conn.execute("SELECT raw_name FROM updates").fetchall()]
    assert names == ["New Box"]


# ── get_updates ───────────────────────────────────────────────────────────────

def test_get_updates_returns_every_row_newest_first(conn, site_id):
    run_id = db.start_run(conn)
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type, created_at) "
        "VALUES (?, ?, 'Older Box', 'new_listing', '2020-01-01 00:00:00')",
        (run_id, site_id),
    )
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type, created_at) "
        "VALUES (?, ?, 'Newer Box', 'new_listing', '2020-06-01 00:00:00')",
        (run_id, site_id),
    )
    conn.commit()

    results = db.get_updates(conn)
    assert [r["raw_name"] for r in results] == ["Newer Box", "Older Box"]
    assert results[0]["site_name"] == "Example"


def test_get_updates_caps_at_the_limit_keeping_the_newest(conn, site_id):
    """The page renders a widget per row, so the feed must not be unbounded."""
    run_id = db.start_run(conn)
    for day in range(1, 6):
        conn.execute(
            "INSERT INTO updates (run_id, site_id, raw_name, event_type, created_at) "
            f"VALUES (?, ?, 'Box {day}', 'new_listing', '2020-01-0{day} 00:00:00')",
            (run_id, site_id),
        )
    conn.commit()

    results = db.get_updates(conn, limit=2)
    assert [r["raw_name"] for r in results] == ["Box 5", "Box 4"]


# ── mark_updates_seen ─────────────────────────────────────────────────────────

def test_mark_updates_seen_sets_seen_for_given_ids_only(conn, site_id):
    run_id = db.start_run(conn)
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) VALUES (?, ?, 'A', 'new_listing')",
        (run_id, site_id),
    )
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) VALUES (?, ?, 'B', 'new_listing')",
        (run_id, site_id),
    )
    conn.commit()

    id_a = conn.execute("SELECT id FROM updates WHERE raw_name='A'").fetchone()["id"]
    db.mark_updates_seen(conn, [id_a])

    rows = {r["raw_name"]: r["seen"] for r in conn.execute("SELECT raw_name, seen FROM updates").fetchall()}
    assert rows["A"] == 1
    assert rows["B"] == 0


def test_mark_all_updates_seen_sets_seen_for_all(conn, site_id):
    run_id = db.start_run(conn)
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) VALUES (?, ?, 'A', 'new_listing')",
        (run_id, site_id),
    )
    conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) VALUES (?, ?, 'B', 'new_listing')",
        (run_id, site_id),
    )
    conn.commit()

    db.mark_all_updates_seen(conn)

    rows = conn.execute("SELECT seen FROM updates").fetchall()
    assert all(r["seen"] == 1 for r in rows)
