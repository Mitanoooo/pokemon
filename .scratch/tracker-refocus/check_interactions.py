"""Drive every widget on the three new pages, and run them against an empty DB.

Complements check_pages.py: that one measures a default render, this one checks
the paths a default render never touches (mark-all-read, cleared multiselect,
site and availability filters, a search with no hits, a DB with no rows).
"""
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pokemon-test.db")
WORKING = Path("/tmp/pokemon-interactions.db")
EMPTY = Path("/tmp/pokemon-empty.db")

EMPTY_MODE = "--empty" in sys.argv

shutil.copy(SOURCE, WORKING)
if not EMPTY_MODE:
    if EMPTY.exists():
        EMPTY.unlink()
    sqlite3.connect(EMPTY).executescript((ROOT / "schema.sql").read_text())

sys.path.insert(0, str(ROOT))
if not EMPTY_MODE:
    os.environ["DB_PATH"] = str(WORKING)
from streamlit.testing.v1 import AppTest  # noqa: E402

failures = 0


def load(page):
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value(page)
    at.run()
    return at


def report(label, at):
    global failures
    problems = [e.value for e in at.exception] + [e.value for e in at.error]
    failures += len(problems)
    shapes = [f.value.shape for f in at.dataframe]
    print(f"{label}: dataframes={shapes} "
          f"info={[i.value for i in at.info]} "
          f"warning={[w.value for w in at.warning]}")
    for problem in problems:
        print("  PROBLEM:", problem)


if EMPTY_MODE:
    # A separate process: get_conn is st.cache_resource, so one process cannot
    # swap the DB out from under an already-cached connection.
    print("\n-- Empty DB")
    for page in ("Updates", "By site", "Search", "Site health"):
        report(page, load(page))
    print("\nfailures:", failures)
    sys.exit(1 if failures else 0)

print("\n-- Updates")
at = load("Updates")
at.button[0].click().run()
unread = sqlite3.connect(WORKING).execute(
    "SELECT COUNT(*) FROM updates WHERE seen = 0").fetchone()[0]
print(f"mark all read -> unread rows in DB: {unread}")
failures += unread != 0
report("after mark all read", at)

at = load("Updates")
at.multiselect[0].set_value([]).run()
report("no event types", at)

at = load("Updates")
at.multiselect[0].set_value(["price_rise"]).run()
report("price rises only", at)

at = load("Updates")
# The site selectbox holds ids, not names, so a label from .options is the wrong
# value to set. Take the id the page would have loaded.
site = sqlite3.connect(WORKING).execute(
    "SELECT id, name FROM sites ORDER BY name").fetchall()[1]
at.selectbox[1].set_value(site[0]).run()
print(f"site filter -> {site[1]} (id {site[0]})")
report("one site", at)

at = load("Updates")
at.selectbox[0].set_value("24 hours").run()
at.number_input[0].set_value(90.0).run()
report("24h and a 90% minimum drop", at)

print("\n-- By site")
at = load("By site")
at.selectbox[1].set_value("preorder").run()
report("preorder only", at)

at = load("By site")
at.text_input[0].set_value("prismatic booster").run()
report("name filter", at)

at = load("By site")
at.text_input[0].set_value("zzzz").run()
report("name filter with no hits", at)

print("\n-- Search")
at = load("Search")
at.text_input[0].set_value("pokemon").run()
report("broad term (hits the cap)", at)

at = load("Search")
at.text_input[0].set_value("zzzz nothing").run()
report("no hits", at)

at = load("Search")
at.text_input[0].set_value("100%").run()
report("a literal percent sign", at)

empty_run = subprocess.run(
    [sys.executable, __file__, str(SOURCE), "--empty"],
    env={**os.environ, "DB_PATH": str(EMPTY)},
)
failures += empty_run.returncode != 0

print("\nfailures:", failures)
sys.exit(1 if failures else 0)
