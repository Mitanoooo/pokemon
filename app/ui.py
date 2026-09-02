"""Bits every page needs: the connection guard, label maps, column configs.

The pages are exec'd by main.py rather than imported, so anything shared has to
live in a module they can import. Project root is on sys.path by then.
"""
import sqlite3
from typing import Optional

import streamlit as st

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
    """Trim a stored timestamp to minutes; seconds are noise in every table."""
    return str(timestamp or "")[:16]


def short(text: Optional[str], cap: int = 80) -> str:
    """Truncate a last_error so one broken site cannot widen the whole table."""
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def link_column(label: str = "Link"):
    """Column config for a product URL: one narrow "open" link per row."""
    return st.column_config.LinkColumn(label, display_text="open", width="small")
