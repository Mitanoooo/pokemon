"""Ticket 18 helper: append a "Ticket 18: ..." sentence to a config's notes.

    venv/bin/python .scratch/tracker-refocus/add_note.py <config.json> '<text>'

The repo keeps one long notes string per config and each ticket appends to it,
so this only concatenates and rewrites with the same json.dumps settings the
other helpers use. Re-running with the same text is a no-op.
"""
import json
import sys
from pathlib import Path


def main():
    path = Path(sys.argv[1])
    text = sys.argv[2].strip()
    config = json.loads(path.read_text())
    notes = (config.get("notes") or "").rstrip()
    if text in notes:
        print(f"{path.name}: already there")
        return
    config["notes"] = f"{notes} {text}".strip() if notes else text
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    print(f"{path.name}: +{len(text)} chars")


if __name__ == "__main__":
    main()
