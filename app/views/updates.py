import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Updates")

# Controls row
col_toggle, col_mark_all, _ = st.columns([2, 2, 6])
with col_toggle:
    show_unmapped = st.toggle("Show unmapped", value=False)
with col_mark_all:
    if st.button("Mark all read"):
        db.mark_all_updates_seen(conn)
        st.rerun()

mapped_only = not show_unmapped
entries = db.get_updates(conn, mapped_only=mapped_only)

if not entries:
    st.info("No updates to show." if mapped_only else "No updates yet.")
    st.stop()

# Collect ids of entries the user marks read this render
ids_to_mark: list[int] = []

_BADGE = {
    "new_listing": "🆕 New listing",
    "price_change": "💰 Price change",
    "back_in_stock": "✅ Back in stock",
}

for entry in entries:
    is_unread = entry["seen"] == 0
    style = "border-left: 4px solid #4CAF50; padding-left: 8px;" if is_unread else ""
    product_label = entry["product_name"] or entry["raw_name"]
    badge = _BADGE.get(entry["event_type"], entry["event_type"])
    run_time = str(entry.get("run_started_at") or entry["created_at"] or "")[:16]

    if entry["event_type"] == "price_change":
        value_str = f"{entry['old_value']} → {entry['new_value']}"
    elif entry["event_type"] == "back_in_stock":
        value_str = "back in stock"
    else:
        value_str = entry["new_value"] or ""

    with st.container():
        if style:
            st.markdown(f'<div style="{style}">', unsafe_allow_html=True)

        left, right = st.columns([10, 1])
        with left:
            st.markdown(
                f"**{badge}** &nbsp; {product_label} &nbsp;·&nbsp; "
                f"{entry['site_name'] or '—'} &nbsp;·&nbsp; "
                f"{value_str} &nbsp;·&nbsp; *{run_time}*"
            )
        with right:
            checked = st.checkbox(
                "Read",
                value=not is_unread,
                key=f"seen_{entry['id']}",
                label_visibility="collapsed",
            )
            if checked and is_unread:
                ids_to_mark.append(entry["id"])

        if style:
            st.markdown("</div>", unsafe_allow_html=True)

if ids_to_mark:
    db.mark_updates_seen(conn, ids_to_mark)
    st.rerun()
