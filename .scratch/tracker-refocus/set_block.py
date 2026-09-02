"""Ticket 18 helper: set one config's availability block, keeping key order.

    venv/bin/python .scratch/tracker-refocus/set_block.py <config.json> '<json block>'
    venv/bin/python .scratch/tracker-refocus/set_block.py <config.json> --drop

The block lands right after "selectors" (where the existing configs keep it) so
the diffs stay readable, and json.dumps with indent 2 matches the repo's style.
"""
import json
import sys
from pathlib import Path


def main():
    path = Path(sys.argv[1])
    config = json.loads(path.read_text())
    arg = sys.argv[2]

    if arg == "--drop":
        config.pop("availability", None)
        out = config
    else:
        block = json.loads(arg)
        out = {}
        for key, value in config.items():
            if key == "availability":
                continue
            out[key] = value
            if key == "selectors":
                out["availability"] = block
        if "availability" not in out:
            out["availability"] = block

    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(out.get("availability"), ensure_ascii=False))


if __name__ == "__main__":
    main()
