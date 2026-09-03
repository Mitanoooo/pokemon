"""Bits every page needs: the connection guard, label maps, column configs.

The pages are exec'd by main.py rather than imported, so anything shared has to
live in a module they can import. Project root is on sys.path by then.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import streamlit as st

# Every table stores UTC and every reader of this app is in Finland, so the
# tables render local time. Named zone, not a fixed offset: the pages have to
# read right on both sides of the EEST/EET switch.
LOCAL_ZONE = ZoneInfo("Europe/Helsinki")

# Row background for a listing matching one of the watch keywords. Amber at low
# alpha, so it reads as a highlight on Streamlit's light and dark themes alike.
HIGHLIGHT_STYLE = "background-color: rgba(255, 196, 0, 0.30)"

AVAILABILITY_LABELS = {
    "in_stock": "in stock",
    "out_of_stock": "out of stock",
    "preorder": "preorder",
    "unknown": "unknown",
}

EVENT_LABELS = {
    "new_listing": "New listing",
    "new_preorder": "Preorder",
    "back_in_stock": "Back in stock",
    "price_drop": "Price drop",
    "price_rise": "Price rise",
}


def connection() -> sqlite3.Connection:
    """Return the connection main.py put in session state, or stop the page.

    main.py is the only router: a page reached any other way has no connection,
    which is what the "No database connection." error means.
    """
    conn = st.session_state.get("conn")
    if conn is None:
        st.error("No database connection.")
        st.stop()
    return conn


def availability_label(value: Optional[str]) -> str:
    """Render one of the four availability states for a table cell."""
    return AVAILABILITY_LABELS.get(value or "unknown", value or "unknown")


def when(timestamp: Optional[str]) -> str:
    """A stored UTC timestamp as Helsinki local time, trimmed to minutes.

    Seconds are noise in every table. Anything that does not parse as the stored
    'YYYY-MM-DD HH:MM:SS' form is passed through trimmed rather than dropped, so
    an odd value stays visible instead of turning into an empty cell.
    """
    text = str(timestamp or "").strip()
    if not text:
        return ""
    try:
        stamp = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text[:16]
    return stamp.replace(tzinfo=timezone.utc).astimezone(LOCAL_ZONE).strftime(
        "%Y-%m-%d %H:%M"
    )


def parse_keywords(text: Optional[str]) -> list[str]:
    """Split a keyword box into keywords: comma-separated, so terms can be phrases.

    'ascended, chaos rising' is two keywords, not three words, because a phrase
    is how the operator names a set.
    """
    return [part.strip() for part in str(text or "").split(",") if part.strip()]


def matches_keywords(text: Optional[str], keywords: Iterable[str]) -> bool:
    """Whether a listing name contains any keyword, ignoring case."""
    haystack = str(text or "").casefold()
    return any(k.casefold() in haystack for k in keywords if k.strip())


def short(text: Optional[str], cap: int = 80) -> str:
    """Truncate a last_error so one broken site cannot widen the whole table."""
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def link_column(label: str = "Link"):
    """Column config for a product URL: one narrow "open" link per row."""
    return st.column_config.LinkColumn(label, display_text="open", width="small")
