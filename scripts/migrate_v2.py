"""
Migration v2: replace products/product_aliases/categories with the
cardmarket_products + name_mappings schema.

Safe to re-run: every step is guarded by existence checks.

Usage:
    python scripts/migrate_v2.py [--db pokemon.db]
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # off during migration only

    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    # ── 1. Create new tables if not already present ───────────────────────────

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cardmarket_products (
            id            INTEGER PRIMARY KEY,
            name          TEXT NOT NULL,
            id_category   INTEGER NOT NULL,
            category_name TEXT NOT NULL,
            id_expansion  INTEGER NOT NULL,
            date_added    TEXT
        );

        CREATE TABLE IF NOT EXISTS name_mappings (
            raw_name              TEXT PRIMARY KEY,
            cardmarket_product_id INTEGER REFERENCES cardmarket_products(id),
            llm_suggestion_id     INTEGER REFERENCES cardmarket_products(id),
            confidence            REAL,
            status                TEXT NOT NULL DEFAULT 'undecided'
                                  CHECK(status IN ('mapped', 'null_mapped', 'undecided')),
            mapped_at             TEXT
        );
    """)

    # ── 2. Migrate price_readings.product_id foreign key target ──────────────
    # SQLite can't ALTER a column constraint, so we recreate the table.
    # All product_id values are currently NULL (verified before migration),
    # so no data remapping is needed.

    if _column_references_products(conn, "price_readings"):
        print("Recreating price_readings with FK → cardmarket_products …")
        conn.executescript("""
            ALTER TABLE price_readings RENAME TO _price_readings_old;

            CREATE TABLE price_readings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER REFERENCES cardmarket_products(id),
                site_id    INTEGER NOT NULL REFERENCES sites(id),
                raw_name   TEXT NOT NULL,
                price      REAL NOT NULL,
                currency   TEXT NOT NULL DEFAULT 'EUR',
                in_stock   INTEGER,
                scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            INSERT INTO price_readings
                (id, product_id, site_id, raw_name, price, currency, in_stock, scraped_at)
            SELECT id, NULL, site_id, raw_name, price, currency, in_stock, scraped_at
            FROM _price_readings_old;

            DROP TABLE _price_readings_old;
        """)
        print("  done.")
    else:
        print("price_readings already points to cardmarket_products — skipping.")

    # ── 3. Migrate thresholds ─────────────────────────────────────────────────

    if "thresholds" in existing_tables and _column_references_products(conn, "thresholds"):
        print("Recreating thresholds with FK → cardmarket_products …")
        conn.executescript("""
            ALTER TABLE thresholds RENAME TO _thresholds_old;

            CREATE TABLE thresholds (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES cardmarket_products(id),
                price      REAL NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            INSERT INTO thresholds (id, product_id, price, active, created_at)
            SELECT id, product_id, price, active, created_at
            FROM _thresholds_old;

            DROP TABLE _thresholds_old;
        """)
        print("  done.")
    else:
        print("thresholds already migrated or empty — skipping.")

    # ── 4. Drop old tables ────────────────────────────────────────────────────

    for table in ("product_aliases", "products", "categories"):
        if table in existing_tables:
            print(f"Dropping {table} …")
            conn.execute(f"DROP TABLE {table}")
            print("  done.")
        else:
            print(f"{table} already gone — skipping.")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()
    print("\nMigration v2 complete.")


def _column_references_products(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if any FK on `table` references the old `products` table."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    return any(row[2] == "products" for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate DB to v2 schema")
    parser.add_argument("--db", default="pokemon.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    migrate(str(db_path))
