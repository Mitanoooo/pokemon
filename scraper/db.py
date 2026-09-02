import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence, Union

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def _as_timestamp(value: Union[str, datetime, None]) -> Optional[str]:
    """Normalise a window bound to the string form the tables store."""
    if isinstance(value, datetime):
        return value.strftime(TIMESTAMP_FORMAT)
    return value


def _name_clauses(
    column: str, text: Union[str, Sequence[str], None]
) -> tuple[list[str], list[str]]:
    """Build one ANDed LIKE clause per whitespace-separated term, with its params.

    `%` and `_` are escaped, so a term the operator types is matched literally
    instead of turning into a wildcard that returns the whole catalogue. LIKE
    ignores case for ASCII, which is as far as SQLite goes without an ICU build.
    """
    if text is None:
        words = []
    elif isinstance(text, str):
        words = text.split()
    else:
        words = [word for term in text for word in term.split()]

    patterns = []
    for word in words:
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        patterns.append(f"%{escaped}%")
    return [f"{column} LIKE ? ESCAPE '\\'" for _ in patterns], patterns


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


def set_listing_availability(
    conn: sqlite3.Connection,
    site_id: int,
    raw_names: Iterable[str],
    availability: str,
    availability_text: Optional[str] = None,
) -> int:
    """Force an availability state onto named listings of one site.

    For listings a run did *not* see: runner uses it to apply a config's
    `absent_means`. last_seen_at and last_run_id deliberately stay put — the
    listing was not seen, and moving them would make a shop that dropped an item
    months ago look freshly scraped on the By site page.

    Returns the number of rows changed.
    """
    names = list(raw_names)
    if not names:
        return 0
    cur = conn.executemany(
        """
        UPDATE listings SET availability = ?, availability_text = ?
        WHERE site_id = ? AND raw_name = ?
        """,
        [(availability, availability_text, site_id, name) for name in names],
    )
    conn.commit()
    return cur.rowcount


# ── listing queries (the app reads these, the scraper does not) ───────────────

def get_sites(conn: sqlite3.Connection) -> list[dict]:
    """Return every site as id and name, name-ordered, for a filter widget.

    get_site_overview would answer this too, but it groups the whole listings
    table to do it, and the Updates page needs nothing but the names.
    """
    rows = conn.execute("SELECT id, name FROM sites ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_site_listings(
    conn: sqlite3.Connection,
    site_id: int,
    availability: Optional[str] = None,
    term: Optional[str] = None,
) -> list[dict]:
    """Return one site's listings, name-ordered, optionally filtered.

    `term` is split on whitespace and ANDed, like the Search page, so typing
    "prismatic etb" narrows instead of finding nothing.
    """
    where = ["site_id = ?"]
    params: list = [site_id]

    if availability:
        where.append("availability = ?")
        params.append(availability)
    name_clauses, patterns = _name_clauses("raw_name", term)
    where += name_clauses
    params += patterns

    rows = conn.execute(
        f"""
        SELECT raw_name, product_url, latest_price, latest_currency,
               availability, availability_text, first_seen_at, last_seen_at
        FROM listings
        WHERE {" AND ".join(where)}
        ORDER BY raw_name
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_listings(
    conn: sqlite3.Connection,
    terms: Union[str, Sequence[str], None],
    limit: int = 500,
) -> list[dict]:
    """Return listings across every site whose raw_name matches all `terms`.

    `terms` is a list of words or a whole query string. No terms means no rows:
    an empty search box should not dump 2,900 listings.

    Rows are ordered by name before site, so the same product from several shops
    lands next to itself and the cap trims names rather than dropping whole
    shops out of the count-by-site summary.
    """
    name_clauses, patterns = _name_clauses("l.raw_name", terms)
    if not name_clauses:
        return []

    rows = conn.execute(
        f"""
        SELECT l.site_id, s.name AS site_name, l.raw_name, l.product_url,
               l.latest_price, l.latest_currency, l.availability, l.last_seen_at
        FROM listings l
        LEFT JOIN sites s ON s.id = l.site_id
        WHERE {" AND ".join(name_clauses)}
        ORDER BY l.raw_name, s.name
        LIMIT ?
        """,
        [*patterns, limit],
    ).fetchall()
    return [dict(r) for r in rows]


def get_site_overview(conn: sqlite3.Connection) -> list[dict]:
    """Return one row per site: listing counts by availability plus health.

    `availability_mode` is NULL for a site whose config has no availability
    block; the By site page renders that as "not tracked" so a gap reads
    differently from a failure. `unknown_share` is None for a site with no
    listings, because 0/0 is not 0% coverage, it is no data.
    """
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.availability_mode, s.last_scraped_at,
               s.consecutive_failures, s.last_error,
               COUNT(l.raw_name) AS listing_count,
               -- COUNT, not SUM: a site with no listings at all would make SUM
               -- NULL, and every count here should read 0 instead.
               COUNT(CASE WHEN l.availability = 'in_stock' THEN 1 END) AS in_stock,
               COUNT(CASE WHEN l.availability = 'out_of_stock' THEN 1 END) AS out_of_stock,
               COUNT(CASE WHEN l.availability = 'preorder' THEN 1 END) AS preorder,
               COUNT(CASE WHEN l.availability = 'unknown' THEN 1 END) AS unknown
        FROM sites s
        LEFT JOIN listings l ON l.site_id = s.id
        GROUP BY s.id
        ORDER BY s.name
        """
    ).fetchall()

    overview = []
    for row in rows:
        site = dict(row)
        total = site["listing_count"]
        site["unknown_share"] = site["unknown"] / total if total else None
        overview.append(site)
    return overview


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


def get_updates(
    conn: sqlite3.Connection,
    event_types: Iterable[str],
    since: Union[str, datetime, None] = None,
    site_id: Optional[int] = None,
    limit: int = 1000,
) -> list[dict]:
    """Return update rows of the given event types since `since`, newest-first.

    An empty `event_types` returns nothing: the page's multiselect cleared means
    "show nothing", and expanding it to everything would be a surprise. `since`
    is a 'YYYY-MM-DD HH:MM:SS' UTC string or a datetime; None drops the window.

    created_at has second granularity and one run writes its whole batch inside
    a second or two, so id breaks the tie and the cap keeps the same rows
    between two calls.

    product_url and latest_currency come from the listing the event names, so a
    price reads as 249 SEK rather than as an ambiguous number. The join is on the
    listings primary key, and a listing that no longer exists leaves both NULL
    rather than dropping the event.
    """
    types = list(event_types)
    if not types:
        return []

    where = [f"u.event_type IN ({','.join('?' * len(types))})"]
    params: list = list(types)

    since_str = _as_timestamp(since)
    if since_str:
        where.append("u.created_at >= ?")
        params.append(since_str)
    if site_id is not None:
        where.append("u.site_id = ?")
        params.append(site_id)
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT u.id, u.run_id, u.site_id, s.name AS site_name,
               u.raw_name, u.event_type, u.old_value, u.new_value,
               u.created_at, u.seen, l.product_url, l.latest_currency
        FROM updates u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN listings l ON l.site_id = u.site_id AND l.raw_name = u.raw_name
        WHERE {" AND ".join(where)}
        ORDER BY u.created_at DESC, u.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def count_unread_updates(conn: sqlite3.Connection) -> int:
    """Count update rows nobody has marked read. The app has no per-user state."""
    return conn.execute("SELECT COUNT(*) FROM updates WHERE seen = 0").fetchone()[0]


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
