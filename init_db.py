"""Apply schema.sql to a SQLite database file. Safe to run multiple times."""
import sqlite3
import sys
from pathlib import Path


def init_db(db_path: str) -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    # idempotent migration: add null_price_count to existing DBs
    try:
        conn.execute("ALTER TABLE sites ADD COLUMN null_price_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.close()
    print(f"Database initialised: {db_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "pokemon.db"
    init_db(path)
