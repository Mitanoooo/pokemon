"""Render every page against a new-schema DB and report exceptions and timings.

Streamlit's own AppTest runner, no browser. Not committed as a test: ticket 20
says the pages are validated by running the app, this is the closest thing that
fits in a terminal.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DB_PATH"] = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pokemon-test.db"
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = ["Updates", "By site", "Search", "Site health"]

failures = 0
for page in PAGES:
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value(page)
    started = time.perf_counter()
    at.run()
    elapsed = time.perf_counter() - started

    print(f"\n=== {page}: {elapsed * 1000:.0f} ms")
    for exception in at.exception:
        failures += 1
        print("EXCEPTION:", exception.value)
    for error in at.error:
        failures += 1
        print("ERROR:", error.value)
    for frame in at.dataframe:
        print("  dataframe", frame.value.shape, list(frame.value.columns))
    for caption in at.caption:
        print("  caption:", caption.value)
    for info in at.info:
        print("  info:", info.value)
    for warning in at.warning:
        print("  warning:", warning.value)

    if page == "Search":
        at.text_input[0].set_value("prismatic etb")
        started = time.perf_counter()
        at.run()
        print(f"--- Search 'prismatic etb': {(time.perf_counter() - started) * 1000:.0f} ms")
        for exception in at.exception:
            failures += 1
            print("EXCEPTION:", exception.value)
        for frame in at.dataframe:
            print("  dataframe", frame.value.shape, list(frame.value.columns))
        for caption in at.caption:
            print("  caption:", caption.value)
        for warning in at.warning:
            print("  warning:", warning.value)

    if page == "Updates":
        at.selectbox[0].set_value("30 days")
        at.number_input[0].set_value(0.0)
        started = time.perf_counter()
        at.run()
        print(f"--- Updates 30d, no min drop: {(time.perf_counter() - started) * 1000:.0f} ms")
        for exception in at.exception:
            failures += 1
            print("EXCEPTION:", exception.value)
        for frame in at.dataframe:
            print("  dataframe", frame.value.shape)
        for caption in at.caption:
            print("  caption:", caption.value)

print("\nfailures:", failures)
sys.exit(1 if failures else 0)
