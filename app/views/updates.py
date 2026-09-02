import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app import ui
from scraper import db

conn = ui.connection()

WINDOWS = {"24 hours": 1, "7 days": 7, "30 days": 30}
DEFAULT_EVENTS = [t for t in ui.EVENT_LABELS if t != "price_rise"]
PRICE_EVENTS = ("price_drop", "price_rise")
ROW_CAP = 1000

heading, action = st.columns([6, 1])
with heading:
    st.title("Updates")
    unread = db.count_unread_updates(conn)
    st.caption(f"{unread} unread" if unread else "Nothing unread")
with action:
    if st.button("Mark all read", width="stretch"):
        db.mark_all_updates_seen(conn)
        st.rerun()

sites = db.get_sites(conn)
site_names = {s["id"]: s["name"] for s in sites}

f_events, f_window, f_site, f_drop = st.columns([4, 1, 2, 1])
with f_events:
    event_types = st.multiselect(
        "Event type",
        list(ui.EVENT_LABELS),
        default=DEFAULT_EVENTS,
        format_func=lambda t: ui.EVENT_LABELS[t],
    )
with f_window:
    window = st.selectbox("Window", list(WINDOWS), index=1)
with f_site:
    # Keyed on site id, not name: two shops could share a name, and None is a
    # cleaner "no filter" than a sentinel string that get_updates has to miss.
    site_id = st.selectbox(
        "Site",
        [None, *site_names],
        format_func=lambda i: "All sites" if i is None else site_names[i],
    )
with f_drop:
    # Applied to price_drop rows only: a 0.10 EUR wobble on a 60 EUR box is not
    # news, and the write path deliberately keeps no magnitude filter.
    min_drop = st.number_input("Min drop %", min_value=0.0, value=2.0, step=0.5)

if not event_types:
    st.info("Pick at least one event type.")
    st.stop()

since = datetime.now(timezone.utc) - timedelta(days=WINDOWS[window])
# One row over the cap, so "capped" is exact instead of guessed from a full page.
rows = db.get_updates(conn, event_types, since, site_id=site_id, limit=ROW_CAP + 1)
capped = len(rows) > ROW_CAP
rows = rows[:ROW_CAP]


def _change_pct(old, new):
    """Percent change between two stored price strings, or None if either is not one."""
    try:
        old_price, new_price = float(old), float(new)
    except (TypeError, ValueError):
        return None
    if old_price == 0:
        return None
    return (new_price - old_price) / old_price * 100


def _movement(row) -> str:
    """The event's payload as one cell: a price move, a state move, or a price."""
    currency = row["latest_currency"] or ""
    if row["event_type"] in PRICE_EVENTS:
        return f"{row['old_value']} → {row['new_value']} {currency}".strip()
    if row["event_type"] == "back_in_stock":
        return (f"{ui.availability_label(row['old_value'])} → "
                f"{ui.availability_label(row['new_value'])}")
    if row["new_value"]:
        return f"{row['new_value']} {currency}".strip()
    return ""


records = []
for row in rows:
    change = _change_pct(row["old_value"], row["new_value"]) \
        if row["event_type"] in PRICE_EVENTS else None
    # An unparseable price keeps the row: the filter should quiet noise, not
    # swallow events whose size cannot be judged.
    if row["event_type"] == "price_drop" and change is not None and abs(change) < min_drop:
        continue
    records.append({
        "Event": ui.EVENT_LABELS.get(row["event_type"], row["event_type"]),
        "Name": row["raw_name"],
        "Site": row["site_name"] or "",
        "Old → new": _movement(row),
        "Change %": change,
        "Link": row["product_url"] or "",
        "When": ui.when(row["created_at"]),
    })

if not records:
    st.info(f"No events in the last {window.lower()} matching these filters.")
    st.stop()

st.caption(f"{len(records)} events")
if capped:
    # The cap is applied before the minimum-drop filter, so the table can show
    # fewer than ROW_CAP rows and still be cut off.
    st.warning(
        f"More than {ROW_CAP} events matched, and the minimum-drop filter runs on "
        "those newest events only. Narrow the window, the site or the event types."
    )

st.dataframe(
    pd.DataFrame(records),
    hide_index=True,
    width="stretch",
    column_config={
        "Change %": st.column_config.NumberColumn(format="%.1f%%", width="small"),
        "Link": ui.link_column(),
    },
)
