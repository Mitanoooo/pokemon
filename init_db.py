"""Apply schema.sql to a SQLite database file. Safe to run multiple times.

This only creates missing tables and indexes. Moving a pre-refocus database to
the four-table shape is scripts/rebuild_db.py's job, and this script refuses to
touch such a database: CREATE TABLE IF NOT EXISTS would leave the old tables
alone and then the new indexes would fail on columns those tables lack.
"""
import sqlite3
import sys
from pathlib import Path

REBUILD_HINT = (
    "{path} predates the four-table schema (listings has no 'availability' column). "
    "Run scripts/rebuild_db.py to build a new database from it instead."
)


class PreRefocusDatabase(RuntimeError):
    pass


def init_db(db_path: str) -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    try:
        _refuse_pre_refocus(conn, db_path)
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
    print(f"Database initialised: {db_path}")


def _refuse_pre_refocus(conn: sqlite3.Connection, db_path: str) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
    if cols and "availability" not in cols:
        raise PreRefocusDatabase(REBUILD_HINT.format(path=db_path))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "pokemon.db"
    try:
        init_db(path)
    except PreRefocusDatabase as exc:
        sys.exit(str(exc))
