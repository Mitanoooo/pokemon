#!/usr/bin/env python3
"""Apply a catalog scrape to the Hetzner DB.

Reads the JSON file produced by the ticket-07 browser scrape (catalog_scrape.json),
SSHes into Hetzner, and marks each matched product as is_curated=1 with its
popularity_rank. Products absent from the scrape are left unchanged.

Usage:
    python scripts/update_catalog.py catalog_scrape.json
"""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

SSH_KEY = Path.home() / ".ssh" / "pokemon-hetzner"
SSH_HOST = "root@65.21.178.63"
PYTHON = "/opt/pokemon/venv/bin/python"

# Inline Python run on the Hetzner server. Receives JSON via stdin.
# Each item: {"cardmarket_product_id": int, "popularity_rank": int}
_UPDATE_SCRIPT = """
import json, sys, sqlite3

items = json.load(sys.stdin)
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
cur = conn.cursor()

matched = not_found = 0
with conn:
    # Clear previous curation so a fresh scrape produces a clean slate.
    cur.execute('UPDATE cardmarket_products SET is_curated = 0, popularity_rank = NULL WHERE is_curated = 1')
    for item in items:
        pid = item['cardmarket_product_id']
        rank = item['popularity_rank']
        cur.execute(
            'UPDATE cardmarket_products SET is_curated = 1, popularity_rank = ? WHERE id = ?',
            (rank, pid)
        )
        if cur.rowcount:
            matched += 1
        else:
            not_found += 1

conn.close()
print(json.dumps({'matched': matched, 'not_found': not_found}))
"""


def load_scrape(path: Path) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        sys.exit(f"Expected a JSON array in {path}, got {type(raw).__name__}")
    return raw


def deduplicate(items: list) -> list:
    """Keep one entry per cardmarket_product_id — lowest popularity_rank wins."""
    best: dict = {}
    for item in items:
        pid = item.get("cardmarket_product_id")
        rank = item.get("popularity_rank")
        if pid is None or rank is None:
            continue
        if pid not in best or rank < best[pid]["popularity_rank"]:
            best[pid] = {"cardmarket_product_id": int(pid), "popularity_rank": int(rank)}
    return list(best.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scrape_file", metavar="JSON", help="catalog_scrape.json from ticket-07 browser scrape")
    args = parser.parse_args()

    path = Path(args.scrape_file)
    if not path.exists():
        sys.exit(f"File not found: {path}")

    raw = load_scrape(path)
    items = deduplicate(raw)

    if not items:
        sys.exit("No valid entries found in scrape file (all missing cardmarket_product_id or popularity_rank)")

    skipped = len(raw) - len(items)
    print(f"Scrape file:  {len(raw)} entries, {len(items)} unique products"
          + (f", {skipped} duplicates/nulls dropped" if skipped else ""))

    cmd_str = f"{PYTHON} -c {shlex.quote(_UPDATE_SCRIPT)}"
    result = subprocess.run(
        ["ssh", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", SSH_HOST, cmd_str],
        input=json.dumps(items, ensure_ascii=False).encode(),
        capture_output=True,
    )

    if result.returncode != 0:
        print(result.stderr.decode(), file=sys.stderr)
        sys.exit(f"SSH command failed (exit {result.returncode})")

    stderr_text = result.stderr.decode().strip()
    if stderr_text:
        print(f"[remote] {stderr_text}", file=sys.stderr)

    response = json.loads(result.stdout.decode())
    print(f"Matched:      {response['matched']}")
    print(f"Not found:    {response['not_found']}")


if __name__ == "__main__":
    main()
