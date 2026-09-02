import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set. Use this everywhere."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── scrape runs ───────────────────────────────────────────────────────────────

def start_run(conn: sqlite3.Connection) -> int:
    """Open a scrape run and return its id. One run per run_all_sites() call."""
    cur = conn.execute("INSERT INTO scrape_runs (started_at) VALUES (?)", (_now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Stamp finished_at on a run. A NULL finished_at means the run was interrupted."""
    conn.execute(
        "UPDATE scrape_runs SET finished_at = ? WHERE id = ?", (_now(), run_id)
    )
    conn.commit()


# ── listings ──────────────────────────────────────────────────────────────────

def get_listing_state(conn: sqlite3.Connection, site_id: int) -> dict[str, dict]:
    """Return the current listings rows for one site, keyed by raw_name.

    Snapshots state *before* a run's upserts so the caller can diff old against
    new; runner._build_update_events is that caller.
    """
    rows = conn.execute(
        """
        SELECT raw_name, product_url, first_seen_at, last_seen_at, last_run_id,
               latest_price, latest_currency, availability, availability_text,
               from_preorder_url
        FROM listings
        WHERE site_id = ?
        """,
        (site_id,),
    ).fetchall()
    return {r["raw_name"]: dict(r) for r in rows}


def upsert_listing(
    conn: sqlite3.Connection,
    site_id: int,
    raw_name: str,
    product_url: Optional[str],
    price: Optional[float],
    currency: Optional[str],
    availability: str = "unknown",
    availability_text: Optional[str] = None,
    run_id: Optional[int] = None,
    from_preorder_url: bool = False,
) -> None:
    """Insert-or-update the listings row for one (site_id, raw_name) sighting.

    Called for *every* scraped product, including ones with no parseable price —
    that is what keeps a price-less product from looking brand new on the next
    run.  first_seen_at is set on insert only; last_seen_at and last_run_id move
    on every sighting.

    A NULL price / currency / product_url does not overwrite a previously known
    value: latest_price is "the last price we could parse", NULL only when no
    price has ever been parsed for this pair.

    availability, availability_text and from_preorder_url, by contrast, are
    overwritten on every sighting, together: they mean "state as of the last time
    we saw this listing", not "best state ever known", and a text kept from an
    older badge would no longer explain the state next to it.
    """
    now = _now()
    url = product_url or None

    conn.execute(
        """
        INSERT INTO listings
            (site_id, raw_name, product_url, first_seen_at, last_seen_at,
             last_run_id, latest_price, latest_currency, availability,
             availability_text, from_preorder_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (site_id, raw_name) DO UPDATE SET
            product_url       = COALESCE(excluded.product_url, listings.product_url),
            last_seen_at      = excluded.last_seen_at,
            last_run_id       = excluded.last_run_id,
            latest_price      = COALESCE(excluded.latest_price, listings.latest_price),
            latest_currency   = COALESCE(excluded.latest_currency, listings.latest_currency),
            availability      = excluded.availability,
            availability_text = excluded.availability_text,
            from_preorder_url = excluded.from_preorder_url
        """,
        (
            site_id,
            raw_name,
            url,
            now,
            now,
            run_id,
            price,
            currency,
            availability or "unknown",
            availability_text,
            int(bool(from_preorder_url)),
        ),
    )
    conn.commit()


# ── updates ───────────────────────────────────────────────────────────────────

def write_updates(conn: sqlite3.Connection, events: list[dict]) -> None:
    """Bulk-insert update events into the updates table."""
    for e in events:
        conn.execute(
            """
            INSERT INTO updates
                (run_id, site_id, raw_name, event_type, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                e.get("run_id"),
                e["site_id"],
                e["raw_name"],
                e["event_type"],
                e.get("old_value"),
                e.get("new_value"),
            ),
        )
    conn.commit()


def prune_updates(conn: sqlite3.Connection, days: int = 30) -> None:
    """Delete update rows older than `days` days."""
    conn.execute(
        "DELETE FROM updates WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()


def get_updates(conn: sqlite3.Connection, limit: int = 500) -> list[dict]:
    """Return the newest `limit` update rows, newest-first.

    created_at has second granularity and one run writes its whole batch inside
    a second or two, so id breaks the tie: which rows the cap keeps is at least
    stable between two calls.

    The cap is a stopgap: the mapping filter that used to keep this page small
    is gone, and the page renders a widget per row, so an unbounded 30-day
    window would render thousands of them. Ticket 20 replaces this with a
    filtered query over event type, window and site.
    """
    rows = conn.execute(
        """
        SELECT u.id, u.run_id, u.site_id, s.name AS site_name,
               u.raw_name, u.event_type, u.old_value, u.new_value,
               u.created_at, u.seen,
               sr.started_at AS run_started_at
        FROM updates u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN scrape_runs sr ON sr.id = u.run_id
        ORDER BY u.created_at DESC, u.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_updates_seen(conn: sqlite3.Connection, ids: list[int]) -> None:
    """Set seen=1 for the given update ids."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"UPDATE updates SET seen = 1 WHERE id IN ({placeholders})", ids)
    conn.commit()


def mark_all_updates_seen(conn: sqlite3.Connection) -> None:
    """Set seen=1 for every row in updates."""
    conn.execute("UPDATE updates SET seen = 1")
    conn.commit()


# ── site health ───────────────────────────────────────────────────────────────

def get_site_health(conn: sqlite3.Connection) -> list[dict]:
    """Return site health rows for the Site health page."""
    rows = conn.execute(
        """
        SELECT name, last_scraped_at, consecutive_failures, null_price_count, last_error
        FROM sites
        ORDER BY consecutive_failures DESC, name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def update_site_health(
    conn: sqlite3.Connection,
    site_id: int,
    success: bool,
    error_text: Optional[str] = None,
    null_price_count: int = 0,
    availability_mode: Optional[str] = None,
) -> None:
    """Record the outcome of one site's run.

    availability_mode is the config's availability forms comma-joined, or NULL
    when the config has no block. It is written on failed runs too: it describes
    the config, not the run, and the By site page reads NULL as "not tracked".
    """
    if success:
        conn.execute(
            """
            UPDATE sites
            SET last_scraped_at = ?,
                consecutive_failures = 0,
                last_error = NULL,
                null_price_count = ?,
                availability_mode = ?
            WHERE id = ?
            """,
            (_now(), null_price_count, availability_mode, site_id),
        )
    else:
        conn.execute(
            """
            UPDATE sites
            SET consecutive_failures = consecutive_failures + 1,
                last_error = ?,
                null_price_count = ?,
                availability_mode = ?
            WHERE id = ?
            """,
            (error_text, null_price_count, availability_mode, site_id),
        )
    conn.commit()
