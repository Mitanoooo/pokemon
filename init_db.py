"""Apply schema.sql to a SQLite database file. Safe to run multiple times."""
import sqlite3
import sys
from pathlib import Path


def init_db(db_path: str) -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    # idempotent column additions for pre-v2 databases
    _add_column_if_missing(conn, "sites", "null_price_count", "INTEGER NOT NULL DEFAULT 0")
    conn.close()
    print(f"Database initialised: {db_path}")


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "pokemon.db"
    init_db(path)
