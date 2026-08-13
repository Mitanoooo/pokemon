#!/usr/bin/env python3
"""Two-mode script for accumulating verified batches and finalizing to production.

Accumulate mode (default — called after each verified batch):
    python scripts/apply_batch.py <batch.csv>

Finalize mode (called once when all batches are verified):
    python scripts/apply_batch.py --finalize
"""

import argparse
import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path

DRAFT_FILE = Path(__file__).parent.parent / "draft_mappings.json"
SSH_KEY = Path.home() / ".ssh" / "pokemon-hetzner"
SSH_HOST = "root@65.21.178.63"
PYTHON = "/opt/pokemon/venv/bin/python"

# Inline Python executed on the Hetzner server via SSH stdin pipe.
# Reads JSON rows from stdin, does DELETE+INSERT+backfill in one transaction.
_FINALIZE_SCRIPT = """
import json, sys, sqlite3
from datetime import datetime, timezone

data = json.load(sys.stdin)
conn = sqlite3.connect('/opt/pokemon/pokemon.db')
cur = conn.cursor()
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def build_row(r):
    status = r['status']
    pid = r.get('cardmarket_product_id')
    ts = now if status in ('mapped', 'null_mapped') else None
    if status == 'mapped':
        return (r['raw_name'], pid, pid, r.get('confidence'), status, ts)
    elif status == 'null_mapped':
        return (r['raw_name'], None, None, r.get('confidence'), status, ts)
    else:  # undecided: llm_suggestion_id = best-guess pid, cardmarket_product_id = NULL
        return (r['raw_name'], None, pid, r.get('confidence'), status, ts)

rows = [build_row(r) for r in data]

with conn:
    cur.execute('DELETE FROM name_mappings')
    cur.executemany(
        'INSERT INTO name_mappings'
        ' (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status, mapped_at)'
        ' VALUES (?,?,?,?,?,?)',
        rows
    )
    cur.execute(
        "UPDATE price_readings"
        " SET product_id = ("
        "  SELECT cardmarket_product_id FROM name_mappings"
        "  WHERE name_mappings.raw_name = price_readings.raw_name"
        "  AND status = 'mapped'"
        " )"
    )
    backfill_count = cur.rowcount

counts = {}
for row in conn.execute('SELECT status, COUNT(*) FROM name_mappings GROUP BY status'):
    counts[row[0]] = row[1]
conn.close()

print(json.dumps({'counts': counts, 'backfill': backfill_count}))
"""


def load_draft() -> dict:
    if DRAFT_FILE.exists():
        rows = json.loads(DRAFT_FILE.read_text(encoding="utf-8"))
        return {r["raw_name"]: r for r in rows}
    return {}


def save_draft(draft: dict) -> None:
    DRAFT_FILE.write_text(
        json.dumps(list(draft.values()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def accumulate(csv_path: Path) -> None:
    draft = load_draft()
    added = overwritten = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw_name = row["raw_name"]
            pid_raw = row.get("cardmarket_product_id", "").strip()
            conf_raw = row.get("confidence", "").strip()
            entry = {
                "raw_name": raw_name,
                "proposed_name": row.get("proposed_name", ""),
                "cardmarket_product_id": int(pid_raw) if pid_raw else None,
                "confidence": float(conf_raw) if conf_raw else None,
                "status": row["status"],
            }
            if raw_name in draft:
                overwritten += 1
            else:
                added += 1
            draft[raw_name] = entry

    save_draft(draft)
    print(f"Rows added:       {added}")
    print(f"Rows overwritten: {overwritten}")
    print(f"Total in draft:   {len(draft)}")


def finalize() -> None:
    if not DRAFT_FILE.exists():
        sys.exit("draft_mappings.json not found — run accumulate mode first")

    data = json.loads(DRAFT_FILE.read_text(encoding="utf-8"))
    if not data:
        sys.exit("draft_mappings.json is empty")

    cmd_str = f"{PYTHON} -c {shlex.quote(_FINALIZE_SCRIPT)}"
    result = subprocess.run(
        ["ssh", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", SSH_HOST, cmd_str],
        input=json.dumps(data, ensure_ascii=False).encode(),
        capture_output=True,
    )

    if result.returncode != 0:
        print(result.stderr.decode(), file=sys.stderr)
        sys.exit(f"SSH command failed (exit {result.returncode})")

    stderr_text = result.stderr.decode().strip()
    if stderr_text:
        print(f"[remote] {stderr_text}", file=sys.stderr)

    response = json.loads(result.stdout.decode())
    counts = response["counts"]
    backfill = response["backfill"]

    print(f"Finalized {sum(counts.values())} rows to production name_mappings:")
    print(f"  mapped:      {counts.get('mapped', 0)}")
    print(f"  null_mapped: {counts.get('null_mapped', 0)}")
    print(f"  undecided:   {counts.get('undecided', 0)}")
    print(f"Backfilled:    {backfill} price_readings rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", nargs="?", metavar="CSV", help="Verified batch CSV to accumulate")
    parser.add_argument("--finalize", action="store_true", help="Push draft_mappings.json to production")
    args = parser.parse_args()

    if args.finalize:
        if args.csv_file:
            parser.error("--finalize does not take a CSV argument")
        finalize()
    else:
        if not args.csv_file:
            parser.error("csv_file is required in accumulate mode")
        accumulate(Path(args.csv_file))


if __name__ == "__main__":
    main()
