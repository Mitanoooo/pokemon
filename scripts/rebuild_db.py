#!/usr/bin/env python3
"""Build a new-schema database from a pre-refocus one.

    python scripts/rebuild_db.py --source pokemon.db [--target pokemon.db.new] [--force]

The target is created from schema.sql and gets sites, scrape_runs, listings and
updates. cardmarket_products, name_mappings, thresholds and price_readings are
left behind: the source file stays on disk as the price-history archive.
"""

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"

TABLES = ("sites", "scrape_runs", "listings", "updates")

_AVAILABILITY_FROM_IN_STOCK = {1: "in_stock", 0: "out_of_stock"}


@dataclass
class TableCounts:
    source: int
    target: int
    expected: int


@dataclass
class RebuildStats:
    tables: Dict[str, TableCounts] = field(default_factory=dict)
    skipped_updates: int = 0

    @property
    def shortfall(self) -> List[str]:
        """Tables whose target holds fewer rows than the copy should have written."""
        return [name for name, c in self.tables.items() if c.target < c.expected]


def copy_all(source: sqlite3.Connection, target: sqlite3.Connection) -> RebuildStats:
    _copy_verbatim(source, target, "sites")
    _copy_verbatim(source, target, "scrape_runs")
    _copy_listings(source, target)
    skipped = _copy_updates(source, target)
    target.commit()
    return collect_stats(source, target, skipped)


def collect_stats(
    source: sqlite3.Connection, target: sqlite3.Connection, skipped_updates: int
) -> RebuildStats:
    stats = RebuildStats(skipped_updates=skipped_updates)
    for table in TABLES:
        src = _count(source, table)
        expected = src - skipped_updates if table == "updates" else src
        stats.tables[table] = TableCounts(
            source=src, target=_count(target, table), expected=expected
        )
    return stats


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _copy_verbatim(source: sqlite3.Connection, target: sqlite3.Connection, table: str) -> None:
    """Copy every column the two schemas share, in the target's order.

    Columns the new schema adds (sites.availability_mode) keep their default;
    columns the old schema had and the new one dropped are ignored.
    """
    src_cols = set(_columns(source, table))
    cols = [c for c in _columns(target, table) if c in src_cols]
    placeholders = ", ".join("?" for _ in cols)
    joined = ", ".join(cols)
    rows = source.execute(f"SELECT {joined} FROM {table}").fetchall()
    target.executemany(
        f"INSERT INTO {table} ({joined}) VALUES ({placeholders})", [tuple(r) for r in rows]
    )


def _copy_listings(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    rows = source.execute(
        """
        SELECT site_id, raw_name, product_url, first_seen_at, last_seen_at,
               last_run_id, latest_price, latest_currency, latest_in_stock
        FROM listings
        """
    ).fetchall()
    target.executemany(
        """
        INSERT INTO listings
            (site_id, raw_name, product_url, first_seen_at, last_seen_at,
             last_run_id, latest_price, latest_currency, availability,
             availability_text, from_preorder_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
        """,
        [tuple(r[:-1]) + (_AVAILABILITY_FROM_IN_STOCK.get(r[-1], "unknown"),) for r in rows],
    )


def _copy_updates(source: sqlite3.Connection, target: sqlite3.Connection) -> int:
    """Copy updates minus product_id, splitting price_change by direction.

    Returns the number of rows skipped because no direction could be read.
    """
    rows = source.execute(
        """
        SELECT id, run_id, site_id, raw_name, event_type, old_value, new_value,
               created_at, seen
        FROM updates
        """
    ).fetchall()

    out, skipped = [], 0
    for row in rows:
        event_type = row[4]
        if event_type == "price_change":
            event_type = _price_direction(row[5], row[6])
            if event_type is None:
                skipped += 1
                continue
        out.append(tuple(row[:4]) + (event_type,) + tuple(row[5:]))

    target.executemany(
        """
        INSERT INTO updates
            (id, run_id, site_id, raw_name, event_type, old_value, new_value,
             created_at, seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        out,
    )
    return skipped


def _price_direction(old_value, new_value) -> Optional[str]:
    """'price_drop', 'price_rise', or None when the pair says neither."""
    try:
        old, new = float(old_value), float(new_value)
    except (TypeError, ValueError):
        return None
    if new < old:
        return "price_drop"
    if new > old:
        return "price_rise"
    return None


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _print_report(stats: RebuildStats) -> None:
    print(f"{'table':<12} {'source':>8} {'target':>8}")
    for name, c in stats.tables.items():
        print(f"{name:<12} {c.source:>8} {c.target:>8}")
    print(f"\nupdates skipped (no price direction): {stats.skipped_updates}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Existing pre-refocus database")
    parser.add_argument("--target", help="Database to create (default: <source>.new)")
    parser.add_argument("--force", action="store_true", help="Replace an existing target")
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    target_path = Path(args.target) if args.target else source_path.with_name(source_path.name + ".new")

    if not source_path.exists():
        print(f"Source database not found: {source_path}", file=sys.stderr)
        return 1
    if target_path.resolve() == source_path.resolve():
        # --force would unlink the source, and it is the only copy of the old
        # price_readings. Write beside it and let the operator do the swap.
        print("Target must differ from the source; the source is the archive.", file=sys.stderr)
        return 1
    if target_path.exists():
        if not args.force:
            print(f"Target already exists: {target_path} (pass --force to replace)", file=sys.stderr)
            return 1
        target_path.unlink()

    source = _open(source_path)
    target = _open(target_path)
    target.executescript(SCHEMA_PATH.read_text())

    try:
        stats = copy_all(source, target)
    finally:
        source.close()
        target.close()

    _print_report(stats)
    if stats.shortfall:
        print(f"\nRows missing in: {', '.join(stats.shortfall)}", file=sys.stderr)
        return 1
    print(f"\nWrote {target_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
