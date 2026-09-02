import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app import ui
from scraper import db

conn = ui.connection()

st.title("By site")

overview = db.get_site_overview(conn)
if not overview:
    st.info("No sites in the database yet.")
    st.stop()

st.subheader("Coverage")
st.caption(
    "Availability mode is what the site's config resolves with. "
    "Not tracked means the config has no availability block, so its listings "
    "read unknown by design rather than by failure."
)

st.dataframe(
    pd.DataFrame([{
        "Site": s["name"],
        "Listings": s["listing_count"],
        "In stock": s["in_stock"],
        "Out of stock": s["out_of_stock"],
        "Preorder": s["preorder"],
        "Unknown": s["unknown"],
        "Unknown %": None if s["unknown_share"] is None else s["unknown_share"] * 100,
        "Availability mode": s["availability_mode"] or "not tracked",
        "Last scraped": ui.when(s["last_scraped_at"]),
        "Failures": s["consecutive_failures"],
        "Last error": ui.short(s["last_error"]),
    } for s in overview]),
    hide_index=True,
    width="stretch",
    column_config={"Unknown %": st.column_config.NumberColumn(format="%.0f%%")},
)

st.subheader("Listings")

site_names = {s["id"]: s["name"] for s in overview}

f_site, f_availability, f_name = st.columns([2, 1, 3])
with f_site:
    # Keyed on id: two shops sharing a name would collapse into one option.
    site_id = st.selectbox("Site", list(site_names), format_func=site_names.get)
with f_availability:
    availability = st.selectbox(
        "Availability",
        ["All", *ui.AVAILABILITY_LABELS],
        format_func=lambda v: "All" if v == "All" else ui.availability_label(v),
    )
with f_name:
    term = st.text_input("Name contains", placeholder="prismatic etb")

listings = db.get_site_listings(
    conn,
    site_id,
    availability=None if availability == "All" else availability,
    term=term,
)

if not listings:
    st.info("No listings match.")
    st.stop()

st.caption(f"{len(listings)} listings")
st.dataframe(
    pd.DataFrame([{
        "Name": row["raw_name"],
        # Numeric, not formatted text: a "9.90 EUR" string sorts before "100.00".
        "Price": row["latest_price"],
        "Cur.": row["latest_currency"] or "",
        "Availability": ui.availability_label(row["availability"]),
        "Link": row["product_url"] or "",
        "First seen": ui.when(row["first_seen_at"]),
        "Last seen": ui.when(row["last_seen_at"]),
    } for row in listings]),
    hide_index=True,
    width="stretch",
    column_config={
        "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
        "Cur.": st.column_config.TextColumn(width="small"),
        "Link": ui.link_column(),
    },
)
