import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app import ui
from scraper import db

conn = ui.connection()

ROW_CAP = 500

st.title("Search")

query = st.text_input(
    "Search every shop",
    placeholder="prismatic etb",
    help="Terms are ANDed, so every word has to appear in the listing name.",
)

if not query.strip():
    st.info("Type a term to search listing names across every shop.")
    st.stop()

# One row over the cap, so "capped" is exact rather than guessed from a full page.
rows = db.search_listings(conn, query, limit=ROW_CAP + 1)
capped = len(rows) > ROW_CAP
rows = rows[:ROW_CAP]

if not rows:
    st.info(f'Nothing matches "{query.strip()}".')
    st.stop()

st.caption(f"{len(rows)} listings in {len({r['site_id'] for r in rows})} shops")
if capped:
    st.warning(
        f"Capped at {ROW_CAP} rows, so the per-shop counts below cover only those. "
        "Add a term to narrow the search."
    )

by_site = Counter(row["site_name"] or "" for row in rows)
st.dataframe(
    pd.DataFrame(
        [{"Site": name, "Matches": count} for name, count in by_site.most_common()]
    ),
    hide_index=True,
    width="content",
)

st.dataframe(
    pd.DataFrame([{
        "Site": row["site_name"] or "",
        "Name": row["raw_name"],
        # Numeric, not formatted text: price-checking across shops means sorting
        # this column, and "9.90 EUR" sorts before "100.00 EUR".
        "Price": row["latest_price"],
        "Cur.": row["latest_currency"] or "",
        "Availability": ui.availability_label(row["availability"]),
        "Link": row["product_url"] or "",
        "Last seen": ui.when(row["last_seen_at"]),
    } for row in rows]),
    hide_index=True,
    width="stretch",
    column_config={
        "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
        "Cur.": st.column_config.TextColumn(width="small"),
        "Link": ui.link_column(),
    },
)
