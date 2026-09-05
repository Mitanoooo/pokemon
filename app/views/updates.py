import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

# Keywords and sites live in the database so they survive reloads and restarts.
stored_keywords = db.get_watch_keywords(conn)
watch_site_ids = db.get_watch_site_ids(conn)

kw_col, add_col, btn_col = st.columns([5, 3, 1])
with kw_col:
    remaining_keywords = st.multiselect(
        "Alert keywords",
        options=stored_keywords,
        default=stored_keywords,
        help="Matching product names trigger a Discord alert and are highlighted below.",
    )
with add_col:
    new_kw_text = st.text_input(
        "add_kw",
        placeholder="Type keyword(s) to add, comma-separated",
        label_visibility="collapsed",
    )
with btn_col:
    st.write("")
    add_kw = st.button("Add", width="stretch", disabled=not new_kw_text.strip())

watched_site_ids = st.multiselect(
    "Alert on sites",
    options=list(site_names.keys()),
    default=watch_site_ids,
    format_func=lambda i: site_names[i],
    help="Any update from these sites triggers a Discord alert, regardless of keyword.",
)

new_kws = remaining_keywords + (ui.parse_keywords(new_kw_text) if add_kw else [])
if new_kws != stored_keywords:
    keywords = db.set_watch_keywords(conn, new_kws)
    st.rerun()
else:
    keywords = stored_keywords

if set(watched_site_ids) != set(watch_site_ids):
    db.set_watch_site_ids(conn, watched_site_ids)
    st.rerun()

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


def _amount(value) -> str:
    """A stored price to two decimals, so a column of them lines up.

    Prices are stored as REAL and as the strings an event was written with, which
    print as '5.9' next to '6.49'. Anything unparseable is shown as it is.
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value or "")


def _price(row) -> str:
    """The event's price as one cell.

    A price move shows both ends, because the move is the news. Every other event
    shows one price: what the thing costs now. new_listing and new_preorder carry
    that price themselves; back_in_stock carries availability states instead, so
    it falls back to the listing's own latest price.
    """
    currency = row["latest_currency"] or ""
    if row["event_type"] in PRICE_EVENTS:
        return f"{_amount(row['old_value'])} → {_amount(row['new_value'])} {currency}".strip()
    price = row["new_value"] if row["event_type"] != "back_in_stock" else None
    if price is None:
        price = row["latest_price"]
    if price is None:
        return ""
    return f"{_amount(price)} {currency}".strip()


records = []
for row in rows:
    change = _change_pct(row["old_value"], row["new_value"]) \
        if row["event_type"] in PRICE_EVENTS else None
    # An unparseable price keeps the row: the filter should quiet noise, not
    # swallow events whose size cannot be judged.
    if row["event_type"] == "price_drop" and change is not None and abs(change) < min_drop:
        continue
    records.append({
        "name": row["raw_name"],
        # The name is the link to the shop's own product page. A listing with no
        # URL keeps its name as plain text instead of a link that goes nowhere.
        "cells": [
            html.escape(ui.EVENT_LABELS.get(row["event_type"], row["event_type"])),
            ui.link(row["product_url"], row["raw_name"]),
            html.escape(row["site_name"] or ""),
            html.escape(_price(row)),
            html.escape(ui.when(row["created_at"])),
        ],
    })

if not records:
    st.info(f"No events in the last {window.lower()} matching these filters.")
    st.stop()

highlight = [ui.matches_keywords(r["name"], keywords) for r in records]
matched = sum(highlight)
caption = f"{len(records)} events"
if keywords:
    caption += f", {matched} matching {', '.join(keywords)}"
st.caption(caption)
if capped:
    # The cap is applied before the minimum-drop filter, so the table can show
    # fewer than ROW_CAP rows and still be cut off.
    st.warning(
        f"More than {ROW_CAP} events matched, and the minimum-drop filter runs on "
        "those newest events only. Narrow the window, the site or the event types."
    )

# An HTML table rather than st.dataframe, because only real anchors can carry the
# product name as the link text. The rows are newest first out of the query, which
# is the order this page is read in, so nothing is lost by not being sortable.
st.markdown(
    ui.html_table(
        ["Event", "Name", "Site", "Price", "When (Helsinki)"],
        [r["cells"] for r in records],
        highlight=highlight,
        nowrap=(0, 3, 4),
    ),
    unsafe_allow_html=True,
)
