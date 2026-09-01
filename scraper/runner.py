import glob
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import sqlite3

from scraper import db
from scraper.fetcher import FetchError, fetch
from scraper.paginator import is_paginated, paginate, source_urls
from scraper.parser import availability_forms, scrape_page

logger = logging.getLogger(__name__)


def _currency_for(source_url: str) -> str:
    host = urlparse(source_url).hostname or ""
    return "SEK" if host.endswith(".se") else "EUR"


def _upsert_site(conn: sqlite3.Connection, config: dict) -> int:
    # A multi-URL config is still one site: its first source URL identifies it.
    url = source_urls(config)[0]
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


def _null_price_count(products: list[dict]) -> int:
    return len([p for p in products if p.get("price") is None])


def _priced_name_count(products: list[dict]) -> int:
    """How many distinct raw_names this run saw with a parseable price.

    Zero of them is what marks a site unhealthy, so a product listed in two
    categories must not inflate the count.
    """
    return len({p["raw_name"] for p in products if p.get("price") is not None})


def _build_update_events(
    site_id: int,
    run_id: int,
    products: list[dict],
    pre_state: dict,
    availability_mode: Optional[str],
) -> list[dict]:
    """Diff products seen this run against the pre-upsert state and return events."""
    # Last occurrence of each raw_name wins (handles multi-page duplicates)
    deduped: dict[str, dict] = {}
    for p in products:
        deduped[p["raw_name"]] = p

    events = []
    for raw_name, p in deduped.items():
        new_price = p.get("price")
        new_availability = p.get("availability")
        old = pre_state.get(raw_name)

        base = {
            "run_id": run_id,
            "site_id": site_id,
            "raw_name": raw_name,
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
                # Direction is decided here rather than by a CAST in the UI
                # query, so the updates(event_type, created_at) index can do
                # the filtering.
                events.append({
                    **base,
                    "event_type": "price_drop" if new_price < old_price else "price_rise",
                    "old_value": str(old_price),
                    "new_value": str(new_price),
                })

            # A site with no availability block reads as all-unknown, so its
            # every-run "unknown" must not look like a stock transition.
            if (availability_mode
                    and old.get("availability") == "out_of_stock"
                    and new_availability == "in_stock"):
                events.append({
                    **base,
                    "event_type": "back_in_stock",
                    "old_value": None,
                    "new_value": "in_stock",
                })

    return events


def _scrape_source_url(
    conn: sqlite3.Connection,
    config: dict,
    site_id: int,
    run_id: int,
    source_url: str,
    sleep_first: bool,
) -> "tuple[list[dict], int]":
    """Scrape every page of one source URL; return its products and page count.

    Listings are upserted page by page, as they are read. sleep_first jitters
    before the very first fetch, which is how the inter-page sleep also lands
    between the source URLs of a multi-URL site.
    """
    site_name = config.get("site_name", source_url)
    currency = _currency_for(source_url)
    urls = paginate(config, source_url)

    products_seen: list[dict] = []
    pages_fetched = 0
    page_counts: list[int] = []
    exhausted_pages = False

    for i, url in enumerate(urls):
        if sleep_first or i > 0:
            time.sleep(random.uniform(1, 4))

        # fetch raises FetchError naming the status code or exception type;
        # run_site's except block records that message as last_error.
        if i == 0:
            html = fetch(url)
        else:
            # Past page 1, a 404 is how WooCommerce and friends say "no such
            # page" — the listing simply ended before max_pages. Anything else
            # (403, 500, a timeout) is a real failure and propagates.
            try:
                html = fetch(url)
            except FetchError as exc:
                if exc.status_code != 404:
                    raise
                logger.info("%s: 404 at %s, stopping pagination", site_name, url)
                exhausted_pages = True
                break

        products = scrape_page(html, config)
        pages_fetched += 1

        if not products:
            logger.info("%s: empty page at %s, stopping pagination", site_name, url)
            exhausted_pages = True
            break

        page_counts.append(len(products))

        # Every sighting lands in listings — including price-less ones, so
        # they do not look brand new next run. This must stay ahead of the
        # valid-price filter in run_site.
        for p in products:
            p["currency"] = currency
            db.upsert_listing(
                conn,
                site_id,
                p["raw_name"],
                product_url=_absolute_url(source_url, p.get("product_url")),
                price=p.get("price"),
                currency=currency,
                availability=p.get("availability", "unknown"),
                availability_text=p.get("availability_text"),
                run_id=run_id,
            )

        products_seen.extend(products)
        skipped = _null_price_count(products)
        if skipped:
            logger.warning(
                "%s: skipped %d product(s) with no parseable price on %s",
                site_name, skipped, url,
            )

    # The last configured page came back as full as the first, so the shop
    # probably has more pages that max_pages is cutting off. A last page with
    # fewer products than the first is the natural end of the listing, and
    # unpaginated configs have nothing to undercount — both stay quiet.
    if (is_paginated(config) and not exhausted_pages
            and page_counts and page_counts[-1] >= page_counts[0]):
        logger.warning(
            "%s: page %d of %d of %s still returned a full page (%d products) — "
            "max_pages may be too low",
            site_name, pages_fetched, len(urls), source_url, page_counts[-1],
        )

    return products_seen, pages_fetched


def run_site(
    config: dict, conn: sqlite3.Connection, run_id: Optional[int] = None
) -> None:
    """Scrape one site and persist its listings and the events they imply.

    A config may name one source URL ("source_url") or several ("source_urls");
    each is paginated independently and all of them feed the same site identity.

    run_id is normally supplied by run_all_sites() so every site in one batch
    shares a run. When called standalone it opens (and closes) its own run.
    """
    site_source_urls = source_urls(config)
    site_name = config.get("site_name", site_source_urls[0])
    site_id = _upsert_site(conn, config)
    availability_mode = availability_forms(config)

    owns_run = run_id is None
    if owns_run:
        run_id = db.start_run(conn)

    all_products: list[dict] = []
    pages_fetched = 0
    try:
        # Snapshot state before this run's upserts for event diffing.
        pre_state = db.get_listing_state(conn, site_id)

        for i, source_url in enumerate(site_source_urls):
            products, pages = _scrape_source_url(
                conn, config, site_id, run_id, source_url, sleep_first=i > 0
            )
            all_products.extend(products)
            pages_fetched += pages

        priced = _priced_name_count(all_products)

        # Generate and persist update events for all products seen this run.
        if all_products:
            events = _build_update_events(
                site_id, run_id, all_products, pre_state, availability_mode
            )
            if events:
                db.write_updates(conn, events)

        if not priced:
            msg = "0 products across all pages"
            logger.warning("%s: pages=%d products=0 — %s", site_name, pages_fetched, msg)
            db.update_site_health(conn, site_id, success=False, error_text=msg,
                                  null_price_count=_null_price_count(all_products),
                                  availability_mode=availability_mode)
            return

        db.update_site_health(conn, site_id, success=True,
                              null_price_count=_null_price_count(all_products),
                              availability_mode=availability_mode)
        logger.info("%s: pages=%d products=%d", site_name, pages_fetched, priced)

    except Exception as exc:
        error_text = str(exc)
        logger.error("%s: error — %s", site_name, error_text)
        db.update_site_health(conn, site_id, success=False, error_text=error_text,
                              null_price_count=_null_price_count(all_products),
                              availability_mode=availability_mode)
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
