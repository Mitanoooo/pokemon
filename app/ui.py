"""Bits every page needs: the connection guard, label maps, column configs.

The pages are exec'd by main.py rather than imported, so anything shared has to
live in a module they can import. Project root is on sys.path by then.
"""
import html
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

import streamlit as st

# Every table stores UTC and every reader of this app is in Finland, so the
# tables render local time. Named zone, not a fixed offset: the pages have to
# read right on both sides of the EEST/EET switch.
LOCAL_ZONE = ZoneInfo("Europe/Helsinki")

# Styling for html_table. Amber at low alpha for a keyword hit, so it reads as a
# highlight on Streamlit's light and dark themes alike, and greys and font sizes
# in relative units so the table sits next to st.dataframe without clashing.
# Scrolls inside its own box rather than stretching the page over 1000 rows.
TABLE_CSS = """
<style>
.utable-wrap { max-height: 70vh; overflow-y: auto; margin-bottom: 1rem; }
.utable { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.utable th { text-align: left; font-weight: 600; padding: 0.4rem 0.5rem;
             border-bottom: 1px solid rgba(128, 128, 128, 0.4); }
.utable td { padding: 0.4rem 0.5rem; vertical-align: top;
             border-bottom: 1px solid rgba(128, 128, 128, 0.15); }
.utable tr.hit td { background-color: rgba(255, 196, 0, 0.30); }
.utable td.nowrap { white-space: nowrap; }
</style>
"""

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


def link(url: Optional[str], text: Optional[str]) -> str:
    """A product name as an anchor to the shop, or as plain text with no URL.

    st.column_config.LinkColumn cannot carry per-row link text: with a Styler it
    takes the displayed value as the href too, which turns a product name into a
    relative link back to this app. So the tables that want a named link build
    their own HTML, and this is the one place that decides what is linkable.

    Only http(s) is followed, because a stored URL is scraped input and a
    'javascript:' one would run in the reader's browser.
    """
    label = html.escape(str(text or ""))
    href = str(url or "").strip()
    if not href.lower().startswith(("http://", "https://")):
        return label
    return (
        f'<a href="{html.escape(href, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{label}</a>'
    )


def html_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    highlight: Optional[Sequence[bool]] = None,
    nowrap: Sequence[int] = (),
) -> str:
    """Render a table whose cells are already HTML.

    Cells are written into the markup as they are, so every caller escapes its own
    text (or builds an anchor with link()). Rows flagged in `highlight` get the
    keyword background; columns listed in `nowrap` keep to one line.
    """
    flags = list(highlight or [])
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for index, row in enumerate(rows):
        cells = "".join(
            f'<td class="nowrap">{c}</td>' if i in nowrap else f"<td>{c}</td>"
            for i, c in enumerate(row)
        )
        hit = " class=\"hit\"" if index < len(flags) and flags[index] else ""
        body.append(f"<tr{hit}>{cells}</tr>")
    return (
        f'{TABLE_CSS}<div class="utable-wrap"><table class="utable">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def short(text: Optional[str], cap: int = 80) -> str:
    """Truncate a last_error so one broken site cannot widen the whole table."""
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def link_column(label: str = "Link"):
    """Column config for a product URL: one narrow "open" link per row."""
    return st.column_config.LinkColumn(label, display_text="open", width="small")
