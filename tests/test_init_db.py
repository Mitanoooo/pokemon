"""Tests for init_db.py."""
import sqlite3

import pytest

import init_db
from tests.test_rebuild_db import OLD_SCHEMA


def _tables(path):
    conn = sqlite3.connect(path)
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _indexes(path):
    conn = sqlite3.connect(path)
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def test_creates_the_four_tables_and_the_indexes(tmp_path):
    path = tmp_path / "fresh.db"

    init_db.init_db(str(path))

    assert _tables(path) >= {"sites", "scrape_runs", "listings", "updates"}
    assert _indexes(path) >= {
        "idx_listings_raw_name",
        "idx_listings_site_availability",
        "idx_updates_created_at",
        "idx_updates_type_created_at",
    }


def test_is_idempotent(tmp_path):
    path = tmp_path / "fresh.db"
    init_db.init_db(str(path))

    init_db.init_db(str(path))

    assert _tables(path) >= {"sites", "scrape_runs", "listings", "updates"}


def test_refuses_a_pre_refocus_database_and_changes_nothing(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()

    with pytest.raises(init_db.PreRefocusDatabase, match="rebuild_db"):
        init_db.init_db(str(path))

    assert not [name for name in _indexes(path) if name.startswith("idx_")]
