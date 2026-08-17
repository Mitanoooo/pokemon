import glob
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import sqlite3

from scraper import db
from scraper.fetcher import fetch
from scraper.paginator import is_paginated, paginate
from scraper.parser import scrape_page

logger = logging.getLogger(__name__)


def _currency_for(source_url: str) -> str:
    host = urlparse(source_url).hostname or ""
    return "SEK" if host.endswith(".se") else "EUR"


def _upsert_site(conn: sqlite3.Connection, config: dict) -> int:
    url = config["source_url"]
    name = config["site_name"]
    row = conn.execute("SELECT id FROM sites WHERE url = ?", (url,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO sites (url, name) VALUES (?, ?)", (url, name))
    conn.commit()
    return cur.lastrowid


def _absolute_url(source_url: str, product_url: Optional[str]) -> Optional[str]:
    """Resolve a scraped href against the site's source_url.

    Returns None for a missing href — urljoin would otherwise hand back the
    source_url itself, which would look like a real item link in the UI.
    """
    if not product_url:
        return None
    return urljoin(source_url, product_url)


def _build_update_events(
    site_id: int,
    run_id: int,
    products: list[dict],
    pre_state: dict,
    post_state: dict,
    stock_mode: Optional[str],
) -> list[dict]:
    """Diff products seen this run against the pre-upsert state and return events."""
    # Last occurrence of each raw_name wins (handles multi-page duplicates)
    deduped: dict[str, dict] = {}
    for p in products:
        deduped[p["raw_name"]] = p

    events = []
    for raw_name, p in deduped.items():
        new_price = p.get("price")
        new_in_stock = p.get("in_stock")
        product_id = post_state.get(raw_name, {}).get("product_id")
        old = pre_state.get(raw_name)

        base = {
            "run_id": run_id,
            "site_id": site_id,
            "raw_name": raw_name,
            "product_id": product_id,
        }

        if old is None:
            events.append({
                **base,
                "event_type": "new_listing",
                "old_value": None,
                "new_value": str(new_price) if new_price is not None else None,
            })
        else:
            old_price = old.get("latest_price")
            price_threshold = 1.0 if p.get("currency") == "SEK" else 0.01
            if (old_price is not None and new_price is not None
                    and abs(new_price - old_price) >= price_threshold):
                events.append({
                    **base,
                    "event_type": "price_change",
                    "old_value": str(old_price),
                    "new_value": str(new_price),
                })

            if (stock_mode and stock_mode != "unknown"
                    and old.get("latest_in_stock") == 0 and new_in_stock):
                events.append({
                    **base,
                    "event_type": "back_in_stock",
                    "old_value": None,
                    "new_value": "in_stock",
                })

    return events


def run_site(
    config: dict, conn: sqlite3.Connection, run_id: Optional[int] = None
) -> None:
    """Scrape one site and persist its listings and price readings.

    run_id is normally supplied by run_all_sites() so every site in one batch
    shares a run. When called standalone it opens (and closes) its own run.
    """
    site_name = config.get("site_name", config["source_url"])
    site_id = _upsert_site(conn, config)
    currency = _currency_for(config["source_url"])
    source_url = config["source_url"]
    stock_mode = config.get("stock_mode")

    owns_run = run_id is None
    if owns_run:
        run_id = db.start_run(conn)

    null_price_count = 0
    try:
        # Snapshot state before this run's upserts for event diffing.
        pre_state = db.get_listing_state(conn, site_id)

        urls = paginate(config)
        all_readings: list[dict] = []
        all_products: list[dict] = []
        pages_fetched = 0
        exhausted_pages = False
        page_counts: list[int] = []

        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(random.uniform(1, 4))

            # fetch raises FetchError naming the status code or exception type;
            # the except block below records that message as last_error.
            html = fetch(url)
            products = scrape_page(html, config)
            pages_fetched += 1

            if not products:
                logger.info("%s: empty page at %s, stopping pagination", site_name, url)
                exhausted_pages = True
                break

            page_counts.append(len(products))

            # Every sighting lands in listings — including price-less ones, so
            # they do not look brand new next run. This must stay ahead of the
            # valid-price filter below.
            for p in products:
                p["currency"] = currency
                db.upsert_listing(
                    conn,
                    site_id,
                    p["raw_name"],
                    product_url=_absolute_url(source_url, p.get("product_url")),
                    price=p.get("price"),
                    currency=currency,
                    in_stock=p.get("in_stock"),
                    run_id=run_id,
                )

            all_products.extend(products)
            valid = [p for p in products if p.get("price") is not None]
            skipped = len(products) - len(valid)
            if skipped:
                null_price_count += skipped
                logger.warning(
                    "%s: skipped %d product(s) with no parseable price on %s",
                    site_name, skipped, url,
                )
            all_readings.extend(valid)

        # The last configured page came back as full as the first, so the shop
        # probably has more pages that max_pages is cutting off. A last page with
        # fewer products than the first is the natural end of the listing, and
        # unpaginated configs have nothing to undercount — both stay quiet.
        if (is_paginated(config) and not exhausted_pages
                and page_counts and page_counts[-1] >= page_counts[0]):
            logger.warning(
                "%s: page %d of %d still returned a full page (%d products) — "
                "max_pages may be too low",
                site_name, pages_fetched, len(urls), page_counts[-1],
            )

        # Generate and persist update events for all products seen this run.
        if all_products:
            post_state = db.get_listing_state(conn, site_id)
            events = _build_update_events(
                site_id, run_id, all_products, pre_state, post_state, stock_mode
            )
            if events:
                db.write_updates(conn, events)

        if not all_readings:
            msg = "0 products across all pages"
            logger.warning("%s: pages=%d products=0 — %s", site_name, pages_fetched, msg)
            db.update_site_health(conn, site_id, success=False, error_text=msg,
                                  null_price_count=null_price_count)
            return

        db.write_readings(conn, site_id, all_readings, run_id=run_id)
        db.update_site_health(conn, site_id, success=True, null_price_count=null_price_count)
        logger.info("%s: pages=%d products=%d", site_name, pages_fetched, len(all_readings))

    except Exception as exc:
        error_text = str(exc)
        logger.error("%s: error — %s", site_name, error_text)
        db.update_site_health(conn, site_id, success=False, error_text=error_text,
                              null_price_count=null_price_count)
    finally:
        if owns_run:
            db.finish_run(conn, run_id)


def run_all_sites(
    db_path: str,
    configs_dir: str = "site_configs",
) -> None:
    conn = db.get_connection(db_path)
    pattern = f"{configs_dir}/*.json"
    config_files = sorted(glob.glob(pattern))

    if not config_files:
        logger.warning("No site config files found in %s", configs_dir)

    # A "run" is the whole batch invocation, so every site shares one run_id.
    run_id = db.start_run(conn)
    logger.info("Starting scrape run %d", run_id)

    try:
        for path in config_files:
            try:
                config = json.loads(open(path).read())
            except Exception as exc:
                logger.error("Failed to load config %s: %s", path, exc)
                continue

            if config.get("disabled"):
                logger.debug("Skipping disabled site: %s", config.get("site_name", path))
                continue

            run_site(config, conn, run_id=run_id)
    finally:
        db.prune_updates(conn)
        db.finish_run(conn, run_id)
