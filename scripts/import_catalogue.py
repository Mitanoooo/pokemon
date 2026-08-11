"""
Load cardmarket_catalogue.json into the cardmarket_products table.

Idempotent: uses INSERT OR IGNORE on the primary key (idProduct).

Usage:
    python scripts/import_catalogue.py [--db pokemon.db] [--catalogue cardmarket_catalogue.json]
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path


def load_catalogue(db_path: str, catalogue_path: str) -> dict:
    data = json.loads(Path(catalogue_path).read_text(encoding="utf-8"))
    products = data["products"]

    conn = sqlite3.connect(db_path)
    inserted = 0
    skipped = 0

    conn.execute("BEGIN")
    for p in products:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO cardmarket_products
                (id, name, id_category, category_name, id_expansion, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                p["idProduct"],
                p["name"],
                p["idCategory"],
                p["categoryName"],
                p["idExpansion"],
                p.get("dateAdded"),
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.execute("COMMIT")
    conn.close()
    return {"inserted": inserted, "skipped": skipped, "total": len(products)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import cardmarket catalogue into SQLite")
    parser.add_argument("--db", default="pokemon.db")
    parser.add_argument("--catalogue", default="cardmarket_catalogue.json")
    args = parser.parse_args()

    for path, label in [(args.db, "database"), (args.catalogue, "catalogue")]:
        if not Path(path).exists():
            print(f"{label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    stats = load_catalogue(args.db, args.catalogue)
    print(
        f"Catalogue import complete: {stats['inserted']} inserted, "
        f"{stats['skipped']} already present, {stats['total']} total"
    )
