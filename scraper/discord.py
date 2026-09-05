import logging
import sqlite3

import requests

logger = logging.getLogger(__name__)

_EVENT_LABELS = {
    "new_listing": "New listing",
    "back_in_stock": "Back in stock",
    "price_drop": "Price drop",
    "price_rise": "Price rise",
    "new_preorder": "New preorder",
    "gone": "Gone",
}
_PRICE_EVENTS = {"price_drop", "price_rise"}


def _matches(name: str, keywords: list[str]) -> bool:
    h = (name or "").casefold()
    return any(k.casefold() in h for k in keywords if k.strip())


def _fmt_price(row: dict) -> str:
    currency = row.get("latest_currency") or ""
    if row["event_type"] in _PRICE_EVENTS:
        try:
            old = f"{float(row['old_value']):.2f}"
            new = f"{float(row['new_value']):.2f}"
            return f"{old} → {new} {currency}".strip()
        except (TypeError, ValueError):
            return ""
    price = row.get("latest_price")
    if price is None:
        return ""
    try:
        return f"{float(price):.2f} {currency}".strip()
    except (TypeError, ValueError):
        return ""


def notify_keyword_matches(
    conn: sqlite3.Connection, run_id: int, webhook_url: str
) -> None:
    keywords = [
        r["keyword"]
        for r in conn.execute(
            "SELECT keyword FROM watch_keywords ORDER BY created_at, keyword"
        ).fetchall()
    ]
    if not keywords:
        return

    rows = conn.execute(
        """
        SELECT u.raw_name, u.event_type, u.old_value, u.new_value,
               s.name AS site_name, l.product_url,
               l.latest_price, l.latest_currency
        FROM updates u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN listings l ON l.site_id = u.site_id AND l.raw_name = u.raw_name
        WHERE u.run_id = ?
        ORDER BY u.id
        """,
        (run_id,),
    ).fetchall()

    matches = [dict(r) for r in rows if _matches(r["raw_name"], keywords)]
    if not matches:
        return

    lines = []
    for r in matches:
        label = _EVENT_LABELS.get(r["event_type"], r["event_type"])
        name = r["raw_name"] or "?"
        url = r.get("product_url")
        name_part = f"[{name}](<{url}>)" if url else name
        site = r.get("site_name") or ""
        price = _fmt_price(r)
        price_part = f" — {price}" if price else ""
        lines.append(f"**{label}** {name_part} @ {site}{price_part}")

    keyword_list = ", ".join(keywords)
    noun = "match" if len(matches) == 1 else "matches"
    content = (
        f"**{len(matches)} keyword {noun}** ({keyword_list}):\n"
        + "\n".join(lines)
    )
    if len(content) > 2000:
        content = content[:1990] + "\n…"

    try:
        resp = requests.post(webhook_url, json={"content": content}, timeout=10)
        resp.raise_for_status()
        logger.info("Discord: sent %d keyword %s", len(matches), noun)
    except Exception as exc:
        logger.warning("Discord notification failed: %s", exc)
