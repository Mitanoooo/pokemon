import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Thresholds")
st.write("Set a price alert threshold per product. The daily digest emails any product currently below its threshold.")

if flash := st.session_state.pop("_flash_thresholds", None):
    st.success(flash)

rows = db.get_thresholds_for_all_products(conn)

if not rows:
    st.info("No products yet.")
    st.stop()

h1, h2, h3, h4 = st.columns([4, 2, 2, 1])
h1.markdown("**Product**")
h2.markdown("**Current lowest price**")
h3.markdown("**Alert threshold**")
h4.markdown("**Active**")
st.divider()

edits = {}

for row in rows:
    price_display = (
        f"{row['lowest_price']:.2f} {row['currency']}"
        if row["lowest_price"] is not None
        else "—"
    )
    current_threshold = float(row["threshold_price"]) if row["threshold_price"] is not None else 0.0
    current_active = bool(row["threshold_active"]) if row["threshold_active"] is not None else False

    c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
    c1.write(row["canonical_name"])
    c2.write(price_display)
    threshold_val = c3.number_input(
        label="",
        min_value=0.0,
        value=current_threshold,
        step=1.0,
        format="%.2f",
        key=f"thr_{row['product_id']}",
        label_visibility="collapsed",
    )
    active_val = c4.checkbox(
        label="",
        value=current_active,
        key=f"act_{row['product_id']}",
        label_visibility="collapsed",
    )
    edits[row["product_id"]] = {"threshold": threshold_val, "active": active_val}

st.divider()
if st.button("Save thresholds", type="primary"):
    saved = 0
    for row in rows:
        pid = row["product_id"]
        edit = edits[pid]
        # Save whenever there is an existing threshold OR a non-zero new value
        # or when the user wants to deactivate an existing one
        has_existing = row["threshold_price"] is not None
        if edit["threshold"] > 0 or has_existing:
            db.save_threshold(conn, pid, edit["threshold"], edit["active"])
            saved += 1
    st.session_state["_flash_thresholds"] = f"Saved {saved} threshold(s)."
    st.rerun()
