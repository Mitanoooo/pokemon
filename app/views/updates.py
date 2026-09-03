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

# The keywords live in the database, not in session state, so they are still here
# after a reload, an app restart or a move to another device. The box is the only
# way to change them: editing it reruns the page, which saves what it now holds.
stored_keywords = db.get_watch_keywords(conn)
f_keywords, f_clear = st.columns([7, 1])
with f_keywords:
    typed = st.text_input(
        "Highlight keywords",
        value=", ".join(stored_keywords),
        placeholder="ascended, chaos rising",
        help="Comma-separated, so a keyword can be a phrase. Matching rows are "
             "highlighted. Saved until you change or clear them.",
    )
with f_clear:
    st.write("")
    cleared = st.button("Clear", width="stretch", disabled=not stored_keywords)

keywords = [] if cleared else ui.parse_keywords(typed)
if keywords != stored_keywords:
    keywords = db.set_watch_keywords(conn, keywords)
    if cleared:
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
        "Event": ui.EVENT_LABELS.get(row["event_type"], row["event_type"]),
        # The name is the link, so the cell holds the URL and a Styler formats it
        # back to the name. A listing with no URL falls back to the name itself:
        # LinkColumn still paints it link-blue but renders no anchor, so it reads
        # as a name that cannot be opened, which is the truth about it.
        "Name": row["product_url"] or row["raw_name"],
        "_name": row["raw_name"],
        "Site": row["site_name"] or "",
        "Price": _price(row),
        "When": ui.when(row["created_at"]),
    })

if not records:
    st.info(f"No events in the last {window.lower()} matching these filters.")
    st.stop()

matched = sum(1 for r in records if ui.matches_keywords(r["_name"], keywords))
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

frame = pd.DataFrame(records)
names = dict(zip(frame["Name"], frame["_name"]))
highlight = frame["_name"].map(lambda n: ui.matches_keywords(n, keywords))
frame = frame.drop(columns=["_name"])

styled = (
    frame.style
    # Column config has no per-row display text, and the docs point at Styler
    # for exactly this: the cell keeps the URL, the table shows the name.
    .format({"Name": lambda url: names.get(url, url)})
    .apply(lambda col: [ui.HIGHLIGHT_STYLE if hit else "" for hit in highlight], axis=0)
)

st.dataframe(
    styled,
    hide_index=True,
    width="stretch",
    column_config={
        "Event": st.column_config.TextColumn(width="small"),
        "Name": st.column_config.LinkColumn("Name", width="large"),
        "Price": st.column_config.TextColumn(width="small"),
        "When": st.column_config.TextColumn("When (Helsinki)", width="small"),
    },
)
