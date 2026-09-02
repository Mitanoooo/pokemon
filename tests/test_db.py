import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

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


@pytest.fixture
def other_site_id(conn):
    cur = conn.execute("INSERT INTO sites (url, name) VALUES ('https://other.fi', 'Other')")
    conn.commit()
    return cur.lastrowid


def _insert_update(conn, site_id, raw_name, event_type="new_listing",
                   created_at="2020-01-01 00:00:00", old_value=None, new_value=None):
    conn.execute(
        "INSERT INTO updates (site_id, raw_name, event_type, old_value, new_value, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (site_id, raw_name, event_type, old_value, new_value, created_at),
    )
    conn.commit()


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


def test_update_site_health_records_the_availability_mode(conn, site_id):
    db.update_site_health(conn, site_id, success=True, availability_mode="text_map,presence")
    row = conn.execute("SELECT availability_mode FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["availability_mode"] == "text_map,presence"


def test_update_site_health_availability_mode_is_null_for_an_untracked_site(conn, site_id):
    db.update_site_health(conn, site_id, success=True, availability_mode="presence")
    db.update_site_health(conn, site_id, success=True, availability_mode=None)
    row = conn.execute("SELECT availability_mode FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["availability_mode"] is None


def test_update_site_health_records_the_availability_mode_on_a_failed_run(conn, site_id):
    """The mode describes the config, so a broken site still reports what it tracks."""
    db.update_site_health(conn, site_id, success=False, error_text="boom",
                         availability_mode="presence")
    row = conn.execute("SELECT availability_mode FROM sites WHERE id=?", (site_id,)).fetchone()
    assert row["availability_mode"] == "presence"


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
        price=54.90, currency="EUR", availability="in_stock", run_id=run_id,
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
                      99.90, "EUR", "in_stock", run_id=first_run)

    # Backdate both timestamps so "first_seen_at unchanged, last_seen_at moved"
    # is observable — _now() has second resolution and both upserts land in the
    # same second otherwise.
    conn.execute("UPDATE listings SET first_seen_at = '2020-01-01 00:00:00', last_seen_at = '2020-01-01 00:00:00'")
    conn.commit()

    second_run = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      89.90, "EUR", "in_stock", run_id=second_run)

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
    assert row["first_seen_at"] == "2020-01-01 00:00:00"
    assert row["last_seen_at"] > "2020-01-01 00:00:00"
    assert row["latest_price"] == 89.90
    assert row["last_run_id"] == second_run


def test_upsert_listing_with_null_price_stores_null_latest_price(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Single Card", "https://example.fi/p/card",
                      None, "EUR", "unknown", run_id=run_id)

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert row["latest_price"] is None
    assert row["raw_name"] == "Single Card"


def test_upsert_listing_null_price_does_not_erase_known_price(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      99.90, "EUR", "in_stock", run_id=run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      None, "EUR", "in_stock", run_id=run_id)

    row = conn.execute("SELECT latest_price FROM listings").fetchone()
    assert row["latest_price"] == 99.90


def test_upsert_listing_empty_url_does_not_erase_known_url(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "https://example.fi/p/1",
                      99.90, "EUR", "in_stock", run_id=run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", "in_stock", run_id=run_id)

    row = conn.execute("SELECT product_url FROM listings").fetchone()
    assert row["product_url"] == "https://example.fi/p/1"


def test_upsert_listing_availability_is_overwritten_not_coalesced(conn, site_id):
    """availability means "state as of the last sighting", so a later unknown
    replaces a known state rather than being COALESCEd away."""
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", "in_stock", run_id=run_id)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", "unknown", run_id=run_id)

    row = conn.execute("SELECT availability FROM listings").fetchone()
    assert row["availability"] == "unknown"


def test_upsert_listing_out_of_stock_sighting_stored_as_out_of_stock(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Booster Box", "", 99.90, "EUR", "out_of_stock", run_id=run_id)

    row = conn.execute("SELECT availability FROM listings").fetchone()
    assert row["availability"] == "out_of_stock"


def test_upsert_listing_stores_the_availability_text(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "preorder",
                      "Ennakkotilaus 12.9.2026", run_id=run_id)

    row = conn.execute("SELECT availability, availability_text FROM listings").fetchone()
    assert row["availability"] == "preorder"
    assert row["availability_text"] == "Ennakkotilaus 12.9.2026"


def test_upsert_listing_availability_text_is_replaced_with_the_state(conn, site_id):
    """A text left over from an older badge would not explain the new state."""
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "preorder",
                      "Ennakkotilaus 12.9.2026", run_id=run_id)
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "in_stock",
                      None, run_id=run_id)

    row = conn.execute("SELECT availability, availability_text FROM listings").fetchone()
    assert row["availability"] == "in_stock"
    assert row["availability_text"] is None


def test_upsert_listing_defaults_to_unknown_availability(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR")

    row = conn.execute("SELECT availability FROM listings").fetchone()
    assert row["availability"] == "unknown"


def test_upsert_listing_defaults_from_preorder_url_to_zero(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR")

    assert conn.execute("SELECT from_preorder_url FROM listings").fetchone()[0] == 0


def test_upsert_listing_stores_from_preorder_url(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "preorder",
                      "(preorder url)", from_preorder_url=True)

    assert conn.execute("SELECT from_preorder_url FROM listings").fetchone()[0] == 1


def test_upsert_listing_from_preorder_url_is_overwritten_not_coalesced(conn, site_id):
    """The flag describes the last sighting, like availability next to it."""
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "preorder",
                      from_preorder_url=True)
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "in_stock",
                      from_preorder_url=False)

    assert conn.execute("SELECT from_preorder_url FROM listings").fetchone()[0] == 0


# ── set_listing_availability ──────────────────────────────────────────────────

def test_set_listing_availability_overwrites_state_and_text(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "in_stock", "Varastossa")

    changed = db.set_listing_availability(conn, site_id, ["Box"], "out_of_stock", "(gone)")

    row = conn.execute("SELECT * FROM listings").fetchone()
    assert (changed, row["availability"], row["availability_text"]) == (
        1, "out_of_stock", "(gone)")


def test_set_listing_availability_leaves_the_sighting_columns_alone(conn, site_id):
    """The listing was not seen: last_seen_at, last_run_id and the price stay."""
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box", "https://example.fi/b", 99.90, "EUR",
                      "in_stock", run_id=run_id)
    before = dict(conn.execute("SELECT * FROM listings").fetchone())

    db.set_listing_availability(conn, site_id, ["Box"], "out_of_stock", "(gone)")

    after = dict(conn.execute("SELECT * FROM listings").fetchone())
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"availability", "availability_text"}


def test_set_listing_availability_only_touches_the_named_site(conn, site_id, other_site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "in_stock")
    db.upsert_listing(conn, other_site_id, "Box", "", 99.90, "EUR", "in_stock")

    db.set_listing_availability(conn, site_id, ["Box"], "out_of_stock")

    states = {r["site_id"]: r["availability"] for r in
              conn.execute("SELECT site_id, availability FROM listings")}
    assert states == {site_id: "out_of_stock", other_site_id: "in_stock"}


def test_set_listing_availability_with_no_names_is_a_no_op(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "", 99.90, "EUR", "in_stock")

    assert db.set_listing_availability(conn, site_id, [], "out_of_stock") == 0
    assert conn.execute("SELECT availability FROM listings").fetchone()[0] == "in_stock"


# ── get_listing_state ─────────────────────────────────────────────────────────

def test_get_listing_state_returns_rows_keyed_by_raw_name(conn, site_id):
    run_id = db.start_run(conn)
    db.upsert_listing(conn, site_id, "Box A", "https://example.fi/a", 10.0, "EUR", "in_stock", run_id=run_id)
    db.upsert_listing(conn, site_id, "Box B", "https://example.fi/b", 20.0, "EUR", "out_of_stock", run_id=run_id)

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
    db.upsert_listing(conn, site_id, "Mine", "", 10.0, "EUR", "in_stock", run_id=run_id)
    db.upsert_listing(conn, other_id, "Theirs", "", 20.0, "EUR", "in_stock", run_id=run_id)

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

def test_get_updates_returns_matching_rows_newest_first(conn, site_id):
    _insert_update(conn, site_id, "Older Box", created_at="2020-01-01 00:00:00")
    _insert_update(conn, site_id, "Newer Box", created_at="2020-06-01 00:00:00")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00")
    assert [r["raw_name"] for r in results] == ["Newer Box", "Older Box"]
    assert results[0]["site_name"] == "Example"


def test_get_updates_filters_by_event_type(conn, site_id):
    _insert_update(conn, site_id, "Dropped", "price_drop")
    _insert_update(conn, site_id, "Risen", "price_rise")
    _insert_update(conn, site_id, "Fresh", "new_listing")

    results = db.get_updates(conn, ["price_drop", "new_listing"], "2019-01-01 00:00:00")
    assert sorted(r["raw_name"] for r in results) == ["Dropped", "Fresh"]


def test_get_updates_with_no_event_types_returns_nothing(conn, site_id):
    """An empty multiselect means "show nothing", not "show everything"."""
    _insert_update(conn, site_id, "Fresh")

    assert db.get_updates(conn, [], "2019-01-01 00:00:00") == []


def test_get_updates_excludes_rows_older_than_the_window(conn, site_id):
    _insert_update(conn, site_id, "Ancient", created_at="2020-01-01 00:00:00")
    _insert_update(conn, site_id, "Recent", created_at="2020-06-01 00:00:00")

    results = db.get_updates(conn, ["new_listing"], "2020-03-01 00:00:00")
    assert [r["raw_name"] for r in results] == ["Recent"]


def test_get_updates_filters_by_site(conn, site_id, other_site_id):
    _insert_update(conn, site_id, "Mine")
    _insert_update(conn, other_site_id, "Theirs")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00", site_id=other_site_id)
    assert [r["raw_name"] for r in results] == ["Theirs"]
    assert results[0]["site_name"] == "Other"


def test_get_updates_caps_at_the_limit_keeping_the_newest(conn, site_id):
    for day in range(1, 6):
        _insert_update(conn, site_id, f"Box {day}", created_at=f"2020-01-0{day} 00:00:00")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00", limit=2)
    assert [r["raw_name"] for r in results] == ["Box 5", "Box 4"]


def test_get_updates_breaks_a_same_second_tie_by_id(conn, site_id):
    """One run writes its whole batch in the same second, so the cap needs id.

    Without the tiebreaker, which rows survive `limit` is up to SQLite and the
    rest stay unreachable until the 30-day prune.
    """
    for n in range(1, 6):
        _insert_update(conn, site_id, f"Box {n}", created_at="2020-01-01 00:00:00")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00", limit=2)
    assert [r["raw_name"] for r in results] == ["Box 5", "Box 4"]


def test_get_updates_carries_the_listing_url_so_a_row_is_one_click(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "https://example.fi/p/box", 9.9, "EUR", "in_stock")
    _insert_update(conn, site_id, "Box", new_value="9.9")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00")
    assert results[0]["product_url"] == "https://example.fi/p/box"


def test_get_updates_carries_the_currency(conn, site_id):
    """A price with no currency is ambiguous: one shop prices in SEK."""
    db.upsert_listing(conn, site_id, "Box", "", 249.0, "SEK", "in_stock")
    _insert_update(conn, site_id, "Box", "price_drop", old_value="299.0", new_value="249.0")

    results = db.get_updates(conn, ["price_drop"], "2019-01-01 00:00:00")
    assert results[0]["latest_currency"] == "SEK"


def test_get_updates_keeps_a_row_whose_listing_is_gone(conn, site_id):
    """An event outlives nothing here, but the join must not drop it either."""
    _insert_update(conn, site_id, "Vanished")

    results = db.get_updates(conn, ["new_listing"], "2019-01-01 00:00:00")
    assert [r["raw_name"] for r in results] == ["Vanished"]
    assert results[0]["product_url"] is None


def test_get_updates_accepts_a_datetime_window(conn, site_id):
    _insert_update(conn, site_id, "Ancient", created_at="2020-01-01 00:00:00")
    _insert_update(conn, site_id, "Recent", created_at="2020-06-01 00:00:00")

    since = datetime(2020, 3, 1, tzinfo=timezone.utc)
    results = db.get_updates(conn, ["new_listing"], since)
    assert [r["raw_name"] for r in results] == ["Recent"]


# ── count_unread_updates ──────────────────────────────────────────────────────

def test_count_unread_updates_counts_only_unseen_rows(conn, site_id):
    _insert_update(conn, site_id, "A")
    _insert_update(conn, site_id, "B")
    conn.execute("UPDATE updates SET seen = 1 WHERE raw_name = 'A'")
    conn.commit()

    assert db.count_unread_updates(conn) == 1


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_listings_ands_every_term(conn, site_id):
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 54.9, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "Prismatic Evolutions Booster Bundle", "", 29.9, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "Surging Sparks ETB", "", 49.9, "EUR", "in_stock")

    results = db.search_listings(conn, ["prismatic", "etb"])
    assert [r["raw_name"] for r in results] == ["Prismatic Evolutions ETB"]


def test_search_listings_ignores_case(conn, site_id):
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 54.9, "EUR", "in_stock")

    assert len(db.search_listings(conn, ["PRISMATIC"])) == 1
    assert len(db.search_listings(conn, ["prismatic"])) == 1


def test_search_listings_matches_terms_in_any_order(conn, site_id):
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 54.9, "EUR", "in_stock")

    assert len(db.search_listings(conn, ["etb", "prismatic"])) == 1


def test_search_listings_spans_sites_and_names_them(conn, site_id, other_site_id):
    db.upsert_listing(conn, site_id, "Surging Sparks ETB", "https://example.fi/p/1",
                      49.9, "EUR", "in_stock")
    db.upsert_listing(conn, other_site_id, "Surging Sparks ETB", "https://other.fi/p/1",
                      44.9, "EUR", "out_of_stock")

    results = db.search_listings(conn, ["surging"])
    assert sorted(r["site_name"] for r in results) == ["Example", "Other"]
    assert {r["availability"] for r in results} == {"in_stock", "out_of_stock"}


def test_search_listings_with_no_terms_returns_nothing(conn, site_id):
    db.upsert_listing(conn, site_id, "Surging Sparks ETB", "", 49.9, "EUR", "in_stock")

    assert db.search_listings(conn, []) == []
    assert db.search_listings(conn, ["   "]) == []


def test_search_listings_treats_a_wildcard_as_a_literal(conn, site_id):
    """Otherwise a typed % matches the whole catalogue."""
    db.upsert_listing(conn, site_id, "Surging Sparks ETB", "", 49.9, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "100% Pokemon", "", 1.0, "EUR", "in_stock")

    results = db.search_listings(conn, ["100%"])
    assert [r["raw_name"] for r in results] == ["100% Pokemon"]


def test_search_listings_caps_at_the_limit(conn, site_id):
    for n in range(10):
        db.upsert_listing(conn, site_id, f"Booster Box {n}", "", 99.9, "EUR", "in_stock")

    assert len(db.search_listings(conn, ["booster"], limit=3)) == 3


def test_search_listings_splits_a_string_query(conn, site_id):
    """The page splits on whitespace, but a bare string must not AND per character."""
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 54.9, "EUR", "in_stock")

    assert len(db.search_listings(conn, "prismatic etb")) == 1


# ── get_site_overview ─────────────────────────────────────────────────────────

def test_get_site_overview_counts_listings_by_availability(conn, site_id):
    for name, availability in [("A", "in_stock"), ("B", "in_stock"),
                               ("C", "out_of_stock"), ("D", "preorder"),
                               ("E", "unknown")]:
        db.upsert_listing(conn, site_id, name, "", 1.0, "EUR", availability)

    row = db.get_site_overview(conn)[0]
    assert row["listing_count"] == 5
    assert row["in_stock"] == 2
    assert row["out_of_stock"] == 1
    assert row["preorder"] == 1
    assert row["unknown"] == 1
    assert row["unknown_share"] == pytest.approx(0.2)


def test_get_site_overview_counts_each_site_separately(conn, site_id, other_site_id):
    db.upsert_listing(conn, site_id, "Mine", "", 1.0, "EUR", "in_stock")
    db.upsert_listing(conn, other_site_id, "Theirs", "", 1.0, "EUR", "unknown")

    rows = {r["name"]: r for r in db.get_site_overview(conn)}
    assert rows["Example"]["listing_count"] == 1
    assert rows["Example"]["unknown"] == 0
    assert rows["Other"]["unknown"] == 1


def test_get_site_overview_includes_a_site_with_no_listings(conn, site_id):
    row = db.get_site_overview(conn)[0]
    assert row["listing_count"] == 0
    assert row["in_stock"] == 0
    assert row["unknown_share"] is None


def test_get_site_overview_reports_a_missing_availability_mode_as_none(conn, site_id):
    """NULL is what the app renders as "not tracked", so it must survive the query."""
    db.upsert_listing(conn, site_id, "A", "", 1.0, "EUR", "unknown")

    row = db.get_site_overview(conn)[0]
    assert row["availability_mode"] is None


def test_get_site_overview_reports_the_configured_availability_mode(conn, site_id):
    db.update_site_health(conn, site_id, success=True, availability_mode="text_map,presence")

    row = db.get_site_overview(conn)[0]
    assert row["availability_mode"] == "text_map,presence"


def test_get_site_overview_carries_the_health_columns(conn, site_id):
    db.update_site_health(conn, site_id, success=False, error_text="HTTP 403")

    row = db.get_site_overview(conn)[0]
    assert row["consecutive_failures"] == 1
    assert row["last_error"] == "HTTP 403"
    assert row["id"] == site_id


# ── get_sites ─────────────────────────────────────────────────────────────────

def test_get_sites_returns_id_and_name_ordered_by_name(conn, site_id, other_site_id):
    assert db.get_sites(conn) == [
        {"id": site_id, "name": "Example"},
        {"id": other_site_id, "name": "Other"},
    ]


# ── get_site_listings ─────────────────────────────────────────────────────────

def test_get_site_listings_returns_only_that_site(conn, site_id, other_site_id):
    db.upsert_listing(conn, site_id, "Mine", "", 1.0, "EUR", "in_stock")
    db.upsert_listing(conn, other_site_id, "Theirs", "", 1.0, "EUR", "in_stock")

    results = db.get_site_listings(conn, site_id)
    assert [r["raw_name"] for r in results] == ["Mine"]


def test_get_site_listings_filters_by_availability(conn, site_id):
    db.upsert_listing(conn, site_id, "Stocked", "", 1.0, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "Gone", "", 1.0, "EUR", "out_of_stock")

    results = db.get_site_listings(conn, site_id, availability="out_of_stock")
    assert [r["raw_name"] for r in results] == ["Gone"]


def test_get_site_listings_filters_by_name_ignoring_case(conn, site_id):
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 1.0, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "Surging Sparks ETB", "", 1.0, "EUR", "in_stock")

    results = db.get_site_listings(conn, site_id, term="PRISMATIC")
    assert [r["raw_name"] for r in results] == ["Prismatic Evolutions ETB"]


def test_get_site_listings_ands_the_name_terms(conn, site_id):
    db.upsert_listing(conn, site_id, "Prismatic Evolutions ETB", "", 1.0, "EUR", "in_stock")
    db.upsert_listing(conn, site_id, "Prismatic Evolutions Bundle", "", 1.0, "EUR", "in_stock")

    results = db.get_site_listings(conn, site_id, term="prismatic etb")
    assert [r["raw_name"] for r in results] == ["Prismatic Evolutions ETB"]


def test_get_site_listings_carries_price_url_and_timestamps(conn, site_id):
    db.upsert_listing(conn, site_id, "Box", "https://example.fi/p/box", 99.9, "EUR",
                      "preorder", "Ennakkotilaus 12.9.2026")

    row = db.get_site_listings(conn, site_id)[0]
    assert row["latest_price"] == 99.9
    assert row["latest_currency"] == "EUR"
    assert row["product_url"] == "https://example.fi/p/box"
    assert row["availability_text"] == "Ennakkotilaus 12.9.2026"
    assert row["first_seen_at"] and row["last_seen_at"]


# ── mark_all_updates_seen ─────────────────────────────────────────────────────

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
