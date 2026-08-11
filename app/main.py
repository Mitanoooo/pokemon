import os
import sqlite3
import sys
from pathlib import Path

import streamlit as st

# Make `scraper` importable when running from the app/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = os.environ.get("DB_PATH", "./pokemon.db")


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


st.set_page_config(page_title="Pokemon Price Tracker", layout="wide")

pages = {
    "Products": "views/products.py",
    "Mapping Review": "views/mappings.py",
    "Site Health": "views/site_health.py",
    "Unknowns": "views/unknowns.py",
    "Categories": "views/categories.py",
    "Thresholds": "views/thresholds.py",
}

st.sidebar.title("Navigation")
selection = st.sidebar.radio("Go to", list(pages.keys()))

conn = get_conn()
st.session_state["conn"] = conn
st.session_state["db_path"] = DB_PATH

page_dir = Path(__file__).parent
page_file = page_dir / pages[selection]

if page_file.exists():
    with open(page_file) as f:
        exec(compile(f.read(), str(page_file), "exec"), {"__file__": str(page_file)})
else:
    st.title(selection)
    st.info(f"Page '{selection}' is not implemented yet.")
