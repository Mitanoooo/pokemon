"""Offline normalisation loop — export unmapped names, import LLM mappings."""
import json
import sqlite3
import sys
from typing import Optional

from scraper import db


def do_export(conn: sqlite3.Connection, output_path: str) -> int:
    rows = db.get_unmapped_raw_names(conn)
    entries = [{"raw_name": r["raw_name"], "site": r["site_name"]} for r in rows]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return len(entries)


def do_import(conn: sqlite3.Connection, input_path: str) -> dict:
    with open(input_path, encoding="utf-8") as f:
        mappings = json.load(f)

    aliases_created = 0
    products_created = 0
    skipped = 0

    for entry in mappings:
        raw_name: str = entry["raw_name"]
        canonical_name: str = entry["canonical_name"]

        # Check if this raw_name already has an alias (any site)
        existing_alias = conn.execute(
            "SELECT id FROM product_aliases WHERE raw_name = ?", (raw_name,)
        ).fetchone()
        if existing_alias:
            skipped += 1
            continue

        # Find or create the product row
        existing_product = conn.execute(
            "SELECT id FROM products WHERE canonical_name = ?", (canonical_name,)
        ).fetchone()
        if existing_product:
            product_id: int = existing_product["id"]
        else:
            cur = conn.execute(
                "INSERT INTO products (canonical_name) VALUES (?)", (canonical_name,)
            )
            conn.commit()
            product_id = cur.lastrowid
            products_created += 1

        # Find the site_id for this raw_name from price_readings
        reading = conn.execute(
            "SELECT site_id FROM price_readings WHERE raw_name = ? LIMIT 1", (raw_name,)
        ).fetchone()
        site_id: Optional[int] = reading["site_id"] if reading else None

        if site_id is not None:
            conn.execute(
                """
                INSERT OR IGNORE INTO product_aliases (product_id, raw_name, site_id)
                VALUES (?, ?, ?)
                """,
                (product_id, raw_name, site_id),
            )
            conn.commit()
            aliases_created += 1
        else:
            skipped += 1

    return {
        "aliases_created": aliases_created,
        "products_created": products_created,
        "skipped": skipped,
    }


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Normaliser — export/import raw name mappings")
    sub = parser.add_subparsers(dest="command")

    exp = sub.add_parser("export", help="Export unmapped raw names to JSON")
    exp.add_argument("output_file", nargs="?", default="pending_names.json")
    exp.add_argument("--db", default="pokemon.db")

    imp = sub.add_parser("import", help="Import canonical name mappings from JSON")
    imp.add_argument("input_file")
    imp.add_argument("--db", default="pokemon.db")

    args = parser.parse_args()

    if args.command == "export":
        conn = db.get_connection(args.db)
        count = do_export(conn, args.output_file)
        print(f"{count} unmapped name(s) written to {args.output_file}")

    elif args.command == "import":
        conn = db.get_connection(args.db)
        stats = do_import(conn, args.input_file)
        print(
            f"aliases created: {stats['aliases_created']}, "
            f"products created: {stats['products_created']}, "
            f"skipped: {stats['skipped']}"
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _main()
