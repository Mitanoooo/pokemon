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


def _resolve_product_id(conn: sqlite3.Connection, raw_name: str) -> Optional[int]:
    """Look up the mapped cardmarket product for a raw_name, or None."""
    row = conn.execute(
        """
        SELECT cardmarket_product_id FROM name_mappings
        WHERE raw_name = ? AND status = 'mapped'
        """,
        (raw_name,),
    ).fetchone()
    return row[0] if row else None


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

    Snapshots state *before* a run's upserts so a caller can diff old against
    new. No production caller yet — the event-diff logic that consumes it is
    the next piece of work.
    """
    rows = conn.execute(
        """
        SELECT raw_name, product_id, product_url, first_seen_at, last_seen_at,
               last_run_id, latest_price, latest_currency, latest_in_stock
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
    in_stock: Optional[bool],
    run_id: Optional[int] = None,
) -> None:
    """Insert-or-update the listings row for one (site_id, raw_name) sighting.

    Called for *every* scraped product, including ones with no parseable price —
    that is what keeps a price-less product from looking brand new on the next
    run.  first_seen_at is set on insert only; last_seen_at and last_run_id move
    on every sighting.

    A NULL price / currency / product_url does not overwrite a previously known
    value: latest_price is "the last price we could parse", NULL only when no
    price has ever been parsed for this pair.
    """
    now = _now()
    product_id = _resolve_product_id(conn, raw_name)
    url = product_url or None
    in_stock_int = None if in_stock is None else int(in_stock)

    conn.execute(
        """
        INSERT INTO listings
            (site_id, raw_name, product_id, product_url, first_seen_at,
             last_seen_at, last_run_id, latest_price, latest_currency,
             latest_in_stock)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (site_id, raw_name) DO UPDATE SET
            product_id      = COALESCE(excluded.product_id, listings.product_id),
            product_url     = COALESCE(excluded.product_url, listings.product_url),
            last_seen_at    = excluded.last_seen_at,
            last_run_id     = excluded.last_run_id,
            latest_price    = COALESCE(excluded.latest_price, listings.latest_price),
            latest_currency = COALESCE(excluded.latest_currency, listings.latest_currency),
            latest_in_stock = COALESCE(excluded.latest_in_stock, listings.latest_in_stock)
        """,
        (
            site_id,
            raw_name,
            product_id,
            url,
            now,
            now,
            run_id,
            price,
            currency,
            in_stock_int,
        ),
    )
    conn.commit()


# ── price readings ────────────────────────────────────────────────────────────

def write_readings(
    conn: sqlite3.Connection,
    site_id: int,
    readings: list[dict],
    run_id: Optional[int] = None,
) -> None:
    """Write a list of raw product readings for one site.

    Each reading dict must have: raw_name, price, currency, in_stock,
    product_url.  product_id is resolved by looking up name_mappings; NULL
    when no mapping exists yet.
    """
    now = _now()
    for r in readings:
        product_id = _resolve_product_id(conn, r["raw_name"])

        conn.execute(
            """
            INSERT INTO price_readings
                (product_id, site_id, raw_name, price, currency, in_stock,
                 scraped_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                site_id,
                r["raw_name"],
                r["price"],
                r.get("currency", "EUR"),
                r.get("in_stock"),
                now,
                run_id,
            ),
        )
    conn.commit()


# ── digest queries ────────────────────────────────────────────────────────────

def get_latest_price_per_site(conn: sqlite3.Connection, product_id: int) -> list[dict]:
    """Return the most recent price reading per site for a given product,
    including the direct item URL from listings where available."""
    rows = conn.execute(
        """
        SELECT pr.site_id, s.name AS site_name, s.url AS site_url,
               pr.price, pr.currency, pr.in_stock, pr.scraped_at,
               pr.raw_name, l.product_url
        FROM price_readings pr
        JOIN sites s ON s.id = pr.site_id
        LEFT JOIN listings l ON l.site_id = pr.site_id AND l.raw_name = pr.raw_name
        WHERE pr.product_id = ?
          AND pr.scraped_at = (
              SELECT MAX(pr2.scraped_at)
              FROM price_readings pr2
              WHERE pr2.product_id = pr.product_id
                AND pr2.site_id = pr.site_id
          )
        """,
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_thresholds(conn: sqlite3.Connection) -> list[dict]:
    """Return all active threshold rows with their product name."""
    rows = conn.execute(
        """
        SELECT t.id, t.product_id, t.price AS threshold_price,
               cp.name AS canonical_name
        FROM thresholds t
        JOIN cardmarket_products cp ON cp.id = t.product_id
        WHERE t.active = 1
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_products_below_threshold(conn: sqlite3.Connection) -> list[dict]:
    """Return rows for each (product, site) where the latest price is below
    the active threshold for that product."""
    rows = conn.execute(
        """
        SELECT cp.name AS canonical_name,
               t.price        AS threshold,
               s.name         AS site_name,
               s.url          AS site_url,
               pr.price,
               pr.currency,
               pr.in_stock,
               pr.scraped_at,
               pr.raw_name,
               pr.product_id
        FROM thresholds t
        JOIN cardmarket_products cp ON cp.id = t.product_id
        JOIN price_readings pr ON pr.product_id = t.product_id
        JOIN sites s ON s.id = pr.site_id
        WHERE t.active = 1
          AND pr.scraped_at = (
              SELECT MAX(pr2.scraped_at)
              FROM price_readings pr2
              WHERE pr2.product_id = pr.product_id
                AND pr2.site_id = pr.site_id
          )
          AND pr.price < t.price
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ── name_mappings (review UI) ────────────────────────────────────────────────

def get_undecided_mappings(conn: sqlite3.Connection) -> list[dict]:
    """Return undecided name_mappings rows enriched with site list, reading
    count, and LLM suggestion name (if any)."""
    rows = conn.execute(
        """
        SELECT
            nm.raw_name,
            nm.llm_suggestion_id,
            nm.confidence,
            cp_sugg.name        AS suggestion_name,
            COUNT(pr.id)        AS reading_count,
            GROUP_CONCAT(DISTINCT s.name) AS sites
        FROM name_mappings nm
        LEFT JOIN price_readings pr ON pr.raw_name = nm.raw_name
        LEFT JOIN sites s ON s.id = pr.site_id
        LEFT JOIN cardmarket_products cp_sugg ON cp_sugg.id = nm.llm_suggestion_id
        WHERE nm.status = 'undecided'
        GROUP BY nm.raw_name
        ORDER BY reading_count DESC, nm.raw_name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_cardmarket_products_for_dropdown(conn: sqlite3.Connection) -> list[dict]:
    """Return all cardmarket products with their category, sorted so that
    categories with the most existing 'mapped' name_mappings float to the top.
    Within each category products are sorted by their own mapping count desc."""
    rows = conn.execute(
        """
        WITH cat_counts AS (
            SELECT cp.category_name, COUNT(nm.raw_name) AS cat_map_count
            FROM cardmarket_products cp
            LEFT JOIN name_mappings nm
                ON nm.cardmarket_product_id = cp.id AND nm.status = 'mapped'
            GROUP BY cp.category_name
        ),
        prod_counts AS (
            SELECT cardmarket_product_id, COUNT(*) AS prod_map_count
            FROM name_mappings
            WHERE status = 'mapped' AND cardmarket_product_id IS NOT NULL
            GROUP BY cardmarket_product_id
        )
        SELECT
            cp.id,
            cp.name,
            cp.category_name,
            COALESCE(cc.cat_map_count, 0)  AS cat_map_count,
            COALESCE(pc.prod_map_count, 0) AS prod_map_count
        FROM cardmarket_products cp
        JOIN cat_counts cc ON cc.category_name = cp.category_name
        LEFT JOIN prod_counts pc ON pc.cardmarket_product_id = cp.id
        ORDER BY cc.cat_map_count DESC, cp.category_name, pc.prod_map_count DESC, cp.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def save_mapping(
    conn: sqlite3.Connection,
    raw_name: str,
    cardmarket_product_id: Optional[int],
) -> None:
    """Resolve an undecided mapping: set status and backfill product_id.

    The denormalised product_id is kept in sync on both price_readings and
    listings, across every site that has seen this raw_name.
    """
    status = "mapped" if cardmarket_product_id is not None else "null_mapped"
    now = _now()
    conn.execute(
        """
        UPDATE name_mappings
        SET cardmarket_product_id = ?,
            status    = ?,
            mapped_at = ?
        WHERE raw_name = ?
        """,
        (cardmarket_product_id, status, now, raw_name),
    )
    conn.execute(
        """
        UPDATE price_readings
        SET product_id = ?
        WHERE raw_name = ?
        """,
        (cardmarket_product_id, raw_name),
    )
    conn.execute(
        """
        UPDATE listings
        SET product_id = ?
        WHERE raw_name = ?
        """,
        (cardmarket_product_id, raw_name),
    )
    conn.commit()


# ── unmapped names (legacy — kept for scraper write_readings lookup) ─────────

def get_unmapped_raw_names(conn: sqlite3.Connection) -> list[dict]:
    """Return distinct raw_names from price_readings with no name_mappings row."""
    rows = conn.execute(
        """
        SELECT DISTINCT pr.raw_name,
               pr.site_id,
               s.name AS site_name
        FROM price_readings pr
        JOIN sites s ON s.id = pr.site_id
        WHERE pr.raw_name NOT IN (SELECT raw_name FROM name_mappings)
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ── updates ───────────────────────────────────────────────────────────────────

def write_updates(conn: sqlite3.Connection, events: list[dict]) -> None:
    """Bulk-insert update events into the updates table."""
    for e in events:
        conn.execute(
            """
            INSERT INTO updates
                (run_id, site_id, raw_name, product_id, event_type, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                e.get("run_id"),
                e["site_id"],
                e["raw_name"],
                e.get("product_id"),
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


def get_updates(conn: sqlite3.Connection, mapped_only: bool = True) -> list[dict]:
    """Return update rows newest-first, optionally limited to mapped listings."""
    query = """
        SELECT u.id, u.run_id, u.site_id, s.name AS site_name,
               u.raw_name, u.product_id,
               COALESCE(cp.name, u.raw_name) AS product_name,
               u.event_type, u.old_value, u.new_value,
               u.created_at, u.seen,
               sr.started_at AS run_started_at
        FROM updates u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN cardmarket_products cp ON cp.id = u.product_id
        LEFT JOIN scrape_runs sr ON sr.id = u.run_id
    """
    if mapped_only:
        query += " WHERE u.product_id IS NOT NULL"
    query += " ORDER BY u.created_at DESC"
    rows = conn.execute(query).fetchall()
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


# ── products page queries ─────────────────────────────────────────────────────

def get_products_summary(conn: sqlite3.Connection) -> list[dict]:
    """Return one row per cardmarket product with lowest current price, cheapest
    site, direct item URL (from listings), in-stock count, and category."""
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT product_id, site_id, price, currency, in_stock, scraped_at,
                   raw_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, site_id
                       ORDER BY scraped_at DESC
                   ) AS rn
            FROM price_readings
            WHERE product_id IS NOT NULL
        ),
        latest_unique AS (
            SELECT product_id, site_id, price, currency, scraped_at, in_stock,
                   raw_name
            FROM latest
            WHERE rn = 1
        ),
        cheapest AS (
            SELECT product_id, site_id, price, currency, raw_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id
                       ORDER BY price
                   ) AS price_rank
            FROM latest_unique
        )
        SELECT
            cp.id,
            cp.name AS canonical_name,
            COALESCE(cp.category_name, 'Uncategorised') AS category,
            NULL AS category_id,
            ch.price AS lowest_price,
            ch.currency,
            s.name AS cheapest_site,
            s.url  AS cheapest_site_url,
            l.product_url,
            (SELECT COUNT(DISTINCT site_id)
             FROM latest_unique lu
             WHERE lu.product_id = cp.id
               AND lu.in_stock = 1) AS sites_in_stock,
            (SELECT MAX(scraped_at)
             FROM latest_unique lu2
             WHERE lu2.product_id = cp.id) AS last_updated
        FROM cardmarket_products cp
        LEFT JOIN cheapest ch ON ch.product_id = cp.id AND ch.price_rank = 1
        LEFT JOIN sites s ON s.id = ch.site_id
        LEFT JOIN listings l ON l.site_id = ch.site_id AND l.raw_name = ch.raw_name
        WHERE EXISTS (
            SELECT 1 FROM price_readings pr WHERE pr.product_id = cp.id
        )
        ORDER BY
            COALESCE(cp.category_name, 'Uncategorised'),
            ch.price
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_product_price_history(conn: sqlite3.Connection, product_id: int) -> list[dict]:
    """Return all price readings for a product, ordered by time."""
    rows = conn.execute(
        """
        SELECT s.name AS site_name, pr.scraped_at, pr.price, pr.currency
        FROM price_readings pr
        JOIN sites s ON s.id = pr.site_id
        WHERE pr.product_id = ?
        ORDER BY pr.scraped_at
        """,
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_site_health(conn: sqlite3.Connection) -> list[dict]:
    """Return site health rows for the Site Health page."""
    rows = conn.execute(
        """
        SELECT name, last_scraped_at, consecutive_failures, null_price_count, last_error
        FROM sites
        ORDER BY consecutive_failures DESC, name
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ── thresholds page ───────────────────────────────────────────────────────────

def get_thresholds_for_all_products(conn: sqlite3.Connection) -> list[dict]:
    """Return all products that have a threshold or price data, with current
    lowest price and threshold info."""
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT product_id, site_id, price, currency,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, site_id
                       ORDER BY scraped_at DESC
                   ) AS rn
            FROM price_readings
            WHERE product_id IS NOT NULL
        ),
        cheapest_ranked AS (
            SELECT product_id, price, currency,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id ORDER BY price
                   ) AS price_rank
            FROM latest
            WHERE rn = 1
        ),
        cheapest AS (
            SELECT product_id, price AS lowest_price, currency
            FROM cheapest_ranked
            WHERE price_rank = 1
        ),
        latest_threshold AS (
            SELECT product_id, price AS threshold_price, active,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id ORDER BY id DESC
                   ) AS rn
            FROM thresholds
        )
        SELECT
            cp.id AS product_id,
            cp.name AS canonical_name,
            ch.lowest_price,
            ch.currency,
            lt.threshold_price,
            lt.active AS threshold_active
        FROM cardmarket_products cp
        JOIN cheapest ch ON ch.product_id = cp.id
        LEFT JOIN latest_threshold lt ON lt.product_id = cp.id AND lt.rn = 1
        ORDER BY cp.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def save_threshold(
    conn: sqlite3.Connection, product_id: int, price: float, active: bool
) -> None:
    """Upsert the threshold for a product — one row per product is maintained."""
    existing = conn.execute(
        "SELECT id FROM thresholds WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (product_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE thresholds SET price = ?, active = ? WHERE id = ?",
            (price, 1 if active else 0, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO thresholds (product_id, price, active) VALUES (?, ?, ?)",
            (product_id, price, 1 if active else 0),
        )
    conn.commit()


# ── site health ───────────────────────────────────────────────────────────────

def update_site_health(
    conn: sqlite3.Connection,
    site_id: int,
    success: bool,
    error_text: Optional[str] = None,
    null_price_count: int = 0,
) -> None:
    if success:
        conn.execute(
            """
            UPDATE sites
            SET last_scraped_at = ?,
                consecutive_failures = 0,
                last_error = NULL,
                null_price_count = ?
            WHERE id = ?
            """,
            (_now(), null_price_count, site_id),
        )
    else:
        conn.execute(
            """
            UPDATE sites
            SET consecutive_failures = consecutive_failures + 1,
                last_error = ?,
                null_price_count = ?
            WHERE id = ?
            """,
            (error_text, null_price_count, site_id),
        )
    conn.commit()
