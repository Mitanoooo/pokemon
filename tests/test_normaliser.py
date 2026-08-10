"""Tests for scraper.normaliser export and import commands."""
import json
import sqlite3
from pathlib import Path

import pytest

from scraper import db
from scraper.normaliser import do_export, do_import

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute("INSERT INTO sites (url, name) VALUES ('https://a.fi', 'Site A')")
    c.execute("INSERT INTO sites (url, name) VALUES ('https://b.fi', 'Site B')")
    c.commit()
    return c


@pytest.fixture
def site_id(conn):
    return conn.execute("SELECT id FROM sites WHERE url='https://a.fi'").fetchone()["id"]


def _seed_reading(conn, site_id, raw_name):
    conn.execute(
        "INSERT INTO price_readings (site_id, raw_name, price, currency) VALUES (?, ?, 9.99, 'EUR')",
        (site_id, raw_name),
    )
    conn.commit()


# ── export ────────────────────────────────────────────────────────────────────

def test_export_writes_valid_json(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "Scarlet & Violet Booster")
    out = tmp_path / "out.json"
    count = do_export(conn, str(out))
    data = json.loads(out.read_text())
    assert count == 1
    assert data[0]["raw_name"] == "Scarlet & Violet Booster"
    assert data[0]["site"] == "Site A"


def test_export_empty_when_all_mapped(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "Some Product")
    pid = db.upsert_product(conn, "Some Product")
    db.upsert_alias(conn, "Some Product", site_id, pid)
    out = tmp_path / "out.json"
    count = do_export(conn, str(out))
    data = json.loads(out.read_text())
    assert count == 0
    assert data == []


def test_export_no_duplicates_across_sites(conn, tmp_path):
    sid_b = conn.execute("SELECT id FROM sites WHERE url='https://b.fi'").fetchone()["id"]
    sid_a = conn.execute("SELECT id FROM sites WHERE url='https://a.fi'").fetchone()["id"]
    _seed_reading(conn, sid_a, "Product X")
    _seed_reading(conn, sid_b, "Product X")  # same name, different site
    out = tmp_path / "out.json"
    count = do_export(conn, str(out))
    # Both (raw_name, site_id) combos are distinct unmapped entries
    assert count == 2


# ── import ────────────────────────────────────────────────────────────────────

def test_import_creates_product_and_alias(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "Scarlet & Violet Booster")
    mappings = [{"raw_name": "Scarlet & Violet Booster", "canonical_name": "Scarlet & Violet — Booster Bundle"}]
    f = tmp_path / "mappings.json"
    f.write_text(json.dumps(mappings))
    stats = do_import(conn, str(f))
    assert stats["aliases_created"] == 1
    assert stats["products_created"] == 1
    assert stats["skipped"] == 0
    row = conn.execute("SELECT canonical_name FROM products").fetchone()
    assert row["canonical_name"] == "Scarlet & Violet — Booster Bundle"


def test_import_reuses_existing_product(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "SV Booster A")
    sid_b = conn.execute("SELECT id FROM sites WHERE url='https://b.fi'").fetchone()["id"]
    _seed_reading(conn, sid_b, "SV Booster B")
    mappings = [
        {"raw_name": "SV Booster A", "canonical_name": "Scarlet & Violet — Booster Bundle"},
        {"raw_name": "SV Booster B", "canonical_name": "Scarlet & Violet — Booster Bundle"},
    ]
    f = tmp_path / "mappings.json"
    f.write_text(json.dumps(mappings))
    stats = do_import(conn, str(f))
    assert stats["products_created"] == 1  # only one product row
    assert stats["aliases_created"] == 2


def test_import_is_idempotent(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "My Product")
    mappings = [{"raw_name": "My Product", "canonical_name": "My Product Canonical"}]
    f = tmp_path / "mappings.json"
    f.write_text(json.dumps(mappings))
    do_import(conn, str(f))
    stats = do_import(conn, str(f))  # second run
    assert stats["skipped"] == 1
    assert stats["aliases_created"] == 0
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert count == 1


def test_import_does_not_overwrite_canonical_name(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "Old Raw")
    pid = db.upsert_product(conn, "Original Canonical")
    db.upsert_alias(conn, "Old Raw", site_id, pid)
    # Attempt to import different canonical for same alias
    mappings = [{"raw_name": "Old Raw", "canonical_name": "New Different Canonical"}]
    f = tmp_path / "mappings.json"
    f.write_text(json.dumps(mappings))
    stats = do_import(conn, str(f))
    assert stats["skipped"] == 1
    # canonical_name must not have changed
    row = conn.execute("SELECT canonical_name FROM products WHERE id=?", (pid,)).fetchone()
    assert row["canonical_name"] == "Original Canonical"


def test_import_reports_counts(conn, site_id, tmp_path):
    _seed_reading(conn, site_id, "A")
    _seed_reading(conn, site_id, "B")
    pid = db.upsert_product(conn, "B Canonical")
    db.upsert_alias(conn, "B", site_id, pid)
    mappings = [
        {"raw_name": "A", "canonical_name": "A Canonical"},
        {"raw_name": "B", "canonical_name": "B Canonical"},  # already mapped → skip
    ]
    f = tmp_path / "mappings.json"
    f.write_text(json.dumps(mappings))
    stats = do_import(conn, str(f))
    assert stats["aliases_created"] == 1
    assert stats["products_created"] == 1
    assert stats["skipped"] == 1
