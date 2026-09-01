"""Tests for scripts/rebuild_db.py."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "rebuild_db.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rebuild_db", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rebuild_db = _load_module()

# The pre-refocus schema, kept here verbatim because schema.sql no longer
# describes it. Only the four tables rebuild_db reads are included.
OLD_SCHEMA = """
CREATE TABLE sites (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    url                  TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    last_scraped_at      TEXT,
    last_error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    null_price_count     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE listings (
    site_id         INTEGER NOT NULL REFERENCES sites(id),
    raw_name        TEXT NOT NULL,
    product_id      INTEGER,
    product_url     TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_run_id     INTEGER REFERENCES scrape_runs(id),
    latest_price    REAL,
    latest_currency TEXT,
    latest_in_stock INTEGER,
    PRIMARY KEY (site_id, raw_name)
);
CREATE TABLE updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER REFERENCES scrape_runs(id),
    site_id    INTEGER NOT NULL REFERENCES sites(id),
    raw_name   TEXT NOT NULL,
    product_id INTEGER,
    event_type TEXT NOT NULL CHECK (event_type IN ('price_change', 'new_listing', 'back_in_stock')),
    old_value  TEXT,
    new_value  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    seen       INTEGER NOT NULL DEFAULT 0
);
"""

NEW_SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


def _connect(script):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(script)
    return conn


@pytest.fixture
def source():
    conn = _connect(OLD_SCHEMA)
    conn.executescript(
        """
        INSERT INTO sites (id, url, name, last_scraped_at, consecutive_failures, null_price_count)
        VALUES (1, 'https://a.fi', 'Shop A', '2026-08-31 10:00:00', 2, 7),
               (2, 'https://b.fi', 'Shop B', NULL, 0, 0);
        INSERT INTO scrape_runs (id, started_at, finished_at)
        VALUES (1, '2026-08-31 10:00:00', '2026-08-31 10:04:00'),
               (2, '2026-08-31 11:00:00', NULL);

        INSERT INTO listings
            (site_id, raw_name, product_id, product_url, first_seen_at, last_seen_at,
             last_run_id, latest_price, latest_currency, latest_in_stock)
        VALUES (1, 'In stock box',  42,   'https://a.fi/1', '2026-01-01 00:00:00',
                '2026-08-31 10:00:00', 1, 129.9, 'EUR', 1),
               (1, 'Sold out box',  NULL, 'https://a.fi/2', '2026-02-01 00:00:00',
                '2026-08-31 10:00:00', 1, 99.5,  'EUR', 0),
               (2, 'Untracked box', NULL, 'https://b.fi/3', '2026-03-01 00:00:00',
                '2026-08-31 10:00:00', 1, NULL,  NULL,  NULL);
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def target():
    return _connect(NEW_SCHEMA)


def _add_update(conn, event_type, old_value=None, new_value=None, site_id=1, raw_name="X"):
    conn.execute(
        """
        INSERT INTO updates (run_id, site_id, raw_name, product_id, event_type,
                             old_value, new_value, created_at)
        VALUES (1, ?, ?, 99, ?, ?, ?, '2026-08-31 10:00:00')
        """,
        (site_id, raw_name, event_type, old_value, new_value),
    )
    conn.commit()


def _rows(conn, sql, *params):
    return [dict(r) for r in conn.execute(sql, params)]


# ── sites and scrape_runs copy verbatim ──────────────────────────────────────

def test_sites_copied_verbatim_with_null_availability_mode(source, target):
    rebuild_db.copy_all(source, target)

    rows = _rows(target, "SELECT * FROM sites ORDER BY id")
    assert [r["url"] for r in rows] == ["https://a.fi", "https://b.fi"]
    assert rows[0]["consecutive_failures"] == 2
    assert rows[0]["null_price_count"] == 7
    assert all(r["availability_mode"] is None for r in rows)


def test_scrape_runs_copied_verbatim(source, target):
    rebuild_db.copy_all(source, target)

    rows = _rows(target, "SELECT * FROM scrape_runs ORDER BY id")
    assert [(r["id"], r["finished_at"]) for r in rows] == [
        (1, "2026-08-31 10:04:00"),
        (2, None),
    ]


# ── listings: product_id dropped, latest_in_stock translated ─────────────────

def test_listings_translate_latest_in_stock_to_availability(source, target):
    rebuild_db.copy_all(source, target)

    rows = _rows(target, "SELECT raw_name, availability FROM listings ORDER BY raw_name")
    assert rows == [
        {"raw_name": "In stock box", "availability": "in_stock"},
        {"raw_name": "Sold out box", "availability": "out_of_stock"},
        {"raw_name": "Untracked box", "availability": "unknown"},
    ]


def test_listings_keep_their_other_columns(source, target):
    rebuild_db.copy_all(source, target)

    row = _rows(target, "SELECT * FROM listings WHERE raw_name = 'In stock box'")[0]
    assert row["site_id"] == 1
    assert row["product_url"] == "https://a.fi/1"
    assert row["first_seen_at"] == "2026-01-01 00:00:00"
    assert row["last_seen_at"] == "2026-08-31 10:00:00"
    assert row["last_run_id"] == 1
    assert row["latest_price"] == 129.9
    assert row["latest_currency"] == "EUR"
    assert row["availability_text"] is None
    assert row["from_preorder_url"] == 0
    assert "product_id" not in row


# ── updates: price_change split by direction ────────────────────────────────

def test_price_change_becomes_price_drop_when_price_fell(source, target):
    _add_update(source, "price_change", old_value="129.9", new_value="99.9")

    rebuild_db.copy_all(source, target)

    assert _rows(target, "SELECT event_type, old_value, new_value FROM updates") == [
        {"event_type": "price_drop", "old_value": "129.9", "new_value": "99.9"}
    ]


def test_price_change_becomes_price_rise_when_price_grew(source, target):
    _add_update(source, "price_change", old_value="99.9", new_value="129.9")

    rebuild_db.copy_all(source, target)

    assert _rows(target, "SELECT event_type FROM updates") == [{"event_type": "price_rise"}]


def test_other_event_types_pass_through(source, target):
    _add_update(source, "new_listing", new_value="20.0", raw_name="A")
    _add_update(source, "back_in_stock", new_value="in_stock", raw_name="B")

    rebuild_db.copy_all(source, target)

    assert _rows(target, "SELECT event_type FROM updates ORDER BY raw_name") == [
        {"event_type": "new_listing"},
        {"event_type": "back_in_stock"},
    ]


def test_updates_drop_product_id_and_keep_the_rest(source, target):
    _add_update(source, "new_listing", new_value="20.0")

    rebuild_db.copy_all(source, target)

    row = _rows(target, "SELECT * FROM updates")[0]
    assert row["run_id"] == 1
    assert row["site_id"] == 1
    assert row["raw_name"] == "X"
    assert row["created_at"] == "2026-08-31 10:00:00"
    assert row["seen"] == 0
    assert "product_id" not in row


@pytest.mark.parametrize(
    "old_value, new_value",
    [
        (None, "99.9"),
        ("129.9", None),
        ("ei tiedossa", "99.9"),
        ("129.9", ""),
        ("99.9", "99.9"),  # no direction to pick
    ],
)
def test_unclassifiable_price_change_is_skipped_and_counted(source, target, old_value, new_value):
    _add_update(source, "new_listing", new_value="20.0", raw_name="keeper")
    _add_update(source, "price_change", old_value=old_value, new_value=new_value)

    stats = rebuild_db.copy_all(source, target)

    assert stats.skipped_updates == 1
    assert _rows(target, "SELECT raw_name FROM updates") == [{"raw_name": "keeper"}]
    assert stats.tables["updates"].source == 2
    assert stats.tables["updates"].target == 1
    assert not stats.shortfall


# ── stats ───────────────────────────────────────────────────────────────────

def test_stats_report_source_and_target_counts_per_table(source, target):
    _add_update(source, "new_listing", new_value="20.0")

    stats = rebuild_db.copy_all(source, target)

    assert {name: (c.source, c.target) for name, c in stats.tables.items()} == {
        "sites": (2, 2),
        "scrape_runs": (2, 2),
        "listings": (3, 3),
        "updates": (1, 1),
    }
    assert stats.skipped_updates == 0
    assert not stats.shortfall


def test_shortfall_names_tables_that_lost_rows(source, target):
    rebuild_db.copy_all(source, target)
    target.execute("DELETE FROM listings WHERE raw_name = 'Sold out box'")
    target.commit()

    stats = rebuild_db.collect_stats(source, target, skipped_updates=0)

    assert stats.shortfall == ["listings"]


# ── CLI: target file handling ───────────────────────────────────────────────

def test_main_creates_the_target_from_the_new_schema(tmp_path, source, capsys):
    src_path = tmp_path / "pokemon.db"
    _dump_to_file(source, src_path)
    target_path = tmp_path / "pokemon.db.new"

    exit_code = rebuild_db.main(["--source", str(src_path), "--target", str(target_path)])

    assert exit_code == 0
    out = sqlite3.connect(target_path)
    tables = {r[0] for r in out.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"sites", "scrape_runs", "listings", "updates", "sqlite_sequence"}
    assert out.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 3
    assert "listings" in capsys.readouterr().out


def test_main_default_target_is_source_plus_new(tmp_path, source):
    src_path = tmp_path / "pokemon.db"
    _dump_to_file(source, src_path)

    assert rebuild_db.main(["--source", str(src_path)]) == 0
    assert (tmp_path / "pokemon.db.new").exists()


def test_main_refuses_to_overwrite_an_existing_target(tmp_path, source, capsys):
    src_path = tmp_path / "pokemon.db"
    _dump_to_file(source, src_path)
    target_path = tmp_path / "pokemon.db.new"
    target_path.write_text("do not clobber me")

    exit_code = rebuild_db.main(["--source", str(src_path), "--target", str(target_path)])

    assert exit_code != 0
    assert target_path.read_text() == "do not clobber me"
    assert "--force" in capsys.readouterr().err


def test_main_force_replaces_an_existing_target(tmp_path, source):
    src_path = tmp_path / "pokemon.db"
    _dump_to_file(source, src_path)
    target_path = tmp_path / "pokemon.db.new"
    target_path.write_text("clobber me")

    exit_code = rebuild_db.main(
        ["--source", str(src_path), "--target", str(target_path), "--force"]
    )

    assert exit_code == 0
    out = sqlite3.connect(target_path)
    assert out.execute("SELECT COUNT(*) FROM sites").fetchone()[0] == 2


def test_main_refuses_a_target_equal_to_the_source(tmp_path, source, capsys):
    src_path = tmp_path / "pokemon.db"
    _dump_to_file(source, src_path)
    before = src_path.read_bytes()

    exit_code = rebuild_db.main(
        ["--source", str(src_path), "--target", str(tmp_path / "." / "pokemon.db"), "--force"]
    )

    assert exit_code != 0
    assert src_path.read_bytes() == before
    assert "differ" in capsys.readouterr().err


def test_main_fails_on_a_missing_source(tmp_path, capsys):
    exit_code = rebuild_db.main(["--source", str(tmp_path / "nope.db")])

    assert exit_code != 0
    assert "nope.db" in capsys.readouterr().err


def _dump_to_file(conn, path):
    """Materialise an in-memory fixture DB as a file so main() can open it."""
    disk = sqlite3.connect(path)
    conn.backup(disk)
    disk.close()
