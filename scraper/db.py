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


# ── products ─────────────────────────────────────────────────────────────────

def upsert_product(conn: sqlite3.Connection, canonical_name: str) -> int:
    """Insert a new product row and return its id. If a product with this
    canonical_name already exists, return the existing id."""
    row = conn.execute(
        "SELECT id FROM products WHERE canonical_name = ?", (canonical_name,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO products (canonical_name) VALUES (?)", (canonical_name,)
    )
    conn.commit()
    return cur.lastrowid


# ── aliases ──────────────────────────────────────────────────────────────────

def upsert_alias(
    conn: sqlite3.Connection, raw_name: str, site_id: int, product_id: int
) -> None:
    """Insert or update a product_alias row. If the (raw_name, site_id) pair
    already exists with a different product_id (e.g. a corrected mapping from
    Streamlit Unknowns), the product_id is updated."""
    conn.execute(
        """
        INSERT INTO product_aliases (product_id, raw_name, site_id)
        VALUES (?, ?, ?)
        ON CONFLICT(raw_name, site_id) DO UPDATE SET product_id = excluded.product_id
        """,
        (product_id, raw_name, site_id),
    )
    conn.commit()


# ── price readings ────────────────────────────────────────────────────────────

def write_readings(
    conn: sqlite3.Connection, site_id: int, readings: list[dict]
) -> None:
    """Write a list of raw product readings for one site.

    Each reading dict must have: raw_name, price, currency, in_stock,
    product_url.  product_id is resolved by looking up product_aliases; NULL
    when no alias exists yet.
    """
    now = _now()
    for r in readings:
        alias_row = conn.execute(
            """
            SELECT product_id FROM product_aliases
            WHERE raw_name = ? AND site_id = ?
            """,
            (r["raw_name"], site_id),
        ).fetchone()
        product_id: Optional[int] = alias_row[0] if alias_row else None

        conn.execute(
            """
            INSERT INTO price_readings
                (product_id, site_id, raw_name, price, currency, in_stock, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                site_id,
                r["raw_name"],
                r["price"],
                r.get("currency", "EUR"),
                r.get("in_stock"),
                now,
            ),
        )
    conn.commit()


# ── digest queries ────────────────────────────────────────────────────────────

def get_latest_price_per_site(conn: sqlite3.Connection, product_id: int) -> list[dict]:
    """Return the most recent price reading per site for a given product."""
    rows = conn.execute(
        """
        SELECT pr.site_id, s.name AS site_name, s.url AS site_url,
               pr.price, pr.currency, pr.in_stock, pr.scraped_at,
               pr.raw_name
        FROM price_readings pr
        JOIN sites s ON s.id = pr.site_id
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
    """Return all active threshold rows with their product canonical_name."""
    rows = conn.execute(
        """
        SELECT t.id, t.product_id, t.price AS threshold_price,
               p.canonical_name
        FROM thresholds t
        JOIN products p ON p.id = t.product_id
        WHERE t.active = 1
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_products_below_threshold(conn: sqlite3.Connection) -> list[dict]:
    """Return rows for each (product, site) where the latest price is below
    the active threshold for that product."""
    rows = conn.execute(
        """
        SELECT p.canonical_name,
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
        JOIN products p ON p.id = t.product_id
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


# ── unmapped names (normaliser + Unknowns page) ───────────────────────────────

def get_unmapped_raw_names(conn: sqlite3.Connection) -> list[dict]:
    """Return distinct (raw_name, site_id, site_name) tuples that appear in
    price_readings but have no entry in product_aliases."""
    rows = conn.execute(
        """
        SELECT DISTINCT pr.raw_name, pr.site_id, s.name AS site_name
        FROM price_readings pr
        JOIN sites s ON s.id = pr.site_id
        WHERE NOT EXISTS (
            SELECT 1 FROM product_aliases pa
            WHERE pa.raw_name = pr.raw_name
              AND pa.site_id  = pr.site_id
        )
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ── products page queries ─────────────────────────────────────────────────────

def get_products_summary(conn: sqlite3.Connection) -> list[dict]:
    """Return one row per canonical product with lowest current price, cheapest
    site, number of sites in stock, and category for the Products list view."""
    rows = conn.execute(
        """
        WITH latest AS (
            -- most recent reading per (product, site)
            SELECT product_id, site_id, price, currency, in_stock, scraped_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, site_id
                       ORDER BY scraped_at DESC
                   ) AS rn
            FROM price_readings
            WHERE product_id IS NOT NULL
        ),
        latest_unique AS (
            SELECT product_id, site_id, price, currency, scraped_at, in_stock
            FROM latest
            WHERE rn = 1
        ),
        cheapest AS (
            -- cheapest current site per product
            SELECT product_id, site_id, price, currency,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id
                       ORDER BY price
                   ) AS price_rank
            FROM latest_unique
        )
        SELECT
            p.id,
            p.canonical_name,
            COALESCE(c.name, 'Uncategorised') AS category,
            c.id AS category_id,
            ch.price AS lowest_price,
            ch.currency,
            s.name AS cheapest_site,
            s.url  AS cheapest_site_url,
            (SELECT COUNT(DISTINCT site_id)
             FROM latest_unique lu
             WHERE lu.product_id = p.id
               AND lu.in_stock = 1) AS sites_in_stock,
            (SELECT MAX(scraped_at)
             FROM latest_unique lu2
             WHERE lu2.product_id = p.id) AS last_updated
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN cheapest ch ON ch.product_id = p.id AND ch.price_rank = 1
        LEFT JOIN sites s ON s.id = ch.site_id
        ORDER BY
            CASE WHEN c.name IS NULL THEN 1 ELSE 0 END,
            COALESCE(c.name, 'Uncategorised'),
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
        SELECT name, last_scraped_at, consecutive_failures, last_error
        FROM sites
        ORDER BY consecutive_failures DESC, name
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ── categories page ──────────────────────────────────────────────────────────

def get_all_categories(conn: sqlite3.Connection) -> list[dict]:
    """Return all categories ordered by name."""
    rows = conn.execute(
        "SELECT id, name FROM categories ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def add_category(conn: sqlite3.Connection, name: str) -> int:
    """Insert a new category and return its id."""
    cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def rename_category(conn: sqlite3.Connection, cat_id: int, new_name: str) -> None:
    """Rename an existing category."""
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id))
    conn.commit()


def get_all_canonical_products(conn: sqlite3.Connection) -> list[dict]:
    """Return all products with a non-NULL canonical_name, ordered by name."""
    rows = conn.execute(
        "SELECT id, canonical_name, category_id FROM products WHERE canonical_name IS NOT NULL ORDER BY canonical_name"
    ).fetchall()
    return [dict(r) for r in rows]


def set_product_category(
    conn: sqlite3.Connection, product_id: int, category_id: Optional[int]
) -> None:
    """Set products.category_id. Pass None to clear the category."""
    conn.execute(
        "UPDATE products SET category_id = ? WHERE id = ?",
        (category_id, product_id),
    )
    conn.commit()


# ── thresholds page ───────────────────────────────────────────────────────────

def get_thresholds_for_all_products(conn: sqlite3.Connection) -> list[dict]:
    """Return all canonical products with their current threshold (if any) and
    the current lowest price across all sites."""
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
            p.id AS product_id,
            p.canonical_name,
            ch.lowest_price,
            ch.currency,
            lt.threshold_price,
            lt.active AS threshold_active
        FROM products p
        LEFT JOIN cheapest ch ON ch.product_id = p.id
        LEFT JOIN latest_threshold lt ON lt.product_id = p.id AND lt.rn = 1
        WHERE p.canonical_name IS NOT NULL
        ORDER BY p.canonical_name
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
) -> None:
    if success:
        conn.execute(
            """
            UPDATE sites
            SET last_scraped_at = ?,
                consecutive_failures = 0,
                last_error = NULL
            WHERE id = ?
            """,
            (_now(), site_id),
        )
    else:
        conn.execute(
            """
            UPDATE sites
            SET consecutive_failures = consecutive_failures + 1,
                last_error = ?
            WHERE id = ?
            """,
            (error_text, site_id),
        )
    conn.commit()
