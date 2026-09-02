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
from scraper.paginator import (
    is_paginated,
    paginate,
    source_urls,
    tagged_source_urls,
)
from scraper.parser import AVAILABILITY_STATES, availability_forms, scrape_page

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


# The availability transitions worth an event, as (previous, new) -> event type.
# "unknown" appears on neither side: a site with no availability block reads
# unknown on every sighting, and pairing that with a real state would report the
# config gap as a stock change. That is what replaced the old stock_mode guard.
_TRANSITION_EVENTS = {
    ("in_stock", "preorder"): "new_preorder",
    ("out_of_stock", "preorder"): "new_preorder",
    ("out_of_stock", "in_stock"): "back_in_stock",
    ("preorder", "in_stock"): "back_in_stock",
}


# What availability_text records for a state that came from a listing's absence
# rather than from anything the page said, in the style of "(preorder url)".
ABSENT_AVAILABILITY_TEXT = "(absent from listing)"

# Above this share of a site's listings, a sweep is likelier to be a truncated
# page than a shop selling out between two hourly runs. Marking most of a
# catalogue absent costs nothing on the way out (out-of-stock is not an event)
# but fires the whole shop as back_in_stock the moment the page renders fully
# again, so the state stays put instead and the run says so.
MAX_ABSENT_SHARE = 0.5


def _absent_state(config: dict) -> Optional[str]:
    """The config's `absent_means` state, or None if it does not use one.

    An unusable value is dropped here rather than at the availability CHECK
    constraint, which would raise mid-run and report a config typo as a
    site-wide scrape failure.
    """
    state = (config.get("availability") or {}).get("absent_means")
    if state is None:
        return None
    if state not in AVAILABILITY_STATES:
        logger.warning(
            "%s: absent_means %r is not one of %s — ignoring it",
            config.get("site_name", ""), state, AVAILABILITY_STATES,
        )
        return None
    return state


def _apply_absent_means(
    conn: sqlite3.Connection,
    config: dict,
    site_id: int,
    products: list[dict],
    pre_state: dict,
) -> int:
    """Mark listings this run did not see with the config's `absent_means`.

    For a source URL filtered to items in stock: an item selling out drops off
    the page instead of changing its badge, so a listing that stops appearing is
    the only out-of-stock signal the shop gives, and without this the row keeps
    its last state for ever and can never come back_in_stock.

    Only for the configs that opt in. Everywhere else a listing disappears for
    too many other reasons (renamed, recategorised, delisted) to read it as out
    of stock, which is why the project ruled that out in general.

    The caller must only call this when every source URL of the site came back:
    a fetch that failed or a page that rendered short would otherwise sweep
    listings that are on the page and in stock.
    """
    absent_state = _absent_state(config)
    if not absent_state or not products or not pre_state:
        return 0

    seen = {p["raw_name"] for p in products}
    absent = [
        name for name, old in pre_state.items()
        if name not in seen and old.get("availability") != absent_state
    ]
    if not absent:
        return 0

    site_name = config.get("site_name", "")
    if len(absent) > MAX_ABSENT_SHARE * len(pre_state):
        logger.warning(
            "%s: %d of %d listing(s) missing from the page — too many to read as "
            "%s, leaving their availability alone",
            site_name, len(absent), len(pre_state), absent_state,
        )
        return 0

    changed = db.set_listing_availability(
        conn, site_id, absent, absent_state, ABSENT_AVAILABILITY_TEXT
    )
    logger.info(
        "%s: %d listing(s) no longer on the page — marked %s",
        site_name, changed, absent_state,
    )
    return changed


def _build_update_events(
    site_id: int,
    run_id: int,
    products: list[dict],
    pre_state: dict,
) -> list[dict]:
    """Diff products seen this run against the pre-upsert state and return events.

    The caller applies the first-run guard: an empty pre_state means a site whose
    listings have never been recorded, and its whole catalogue must not land in
    the feed as new.
    """
    # Last occurrence of each raw_name wins (handles multi-page duplicates)
    deduped: dict[str, dict] = {}
    for p in products:
        deduped[p["raw_name"]] = p

    events = []
    for raw_name, p in deduped.items():
        new_price = p.get("price")
        new_availability = p.get("availability") or "unknown"
        new_price_str = str(new_price) if new_price is not None else None
        old = pre_state.get(raw_name)

        base = {
            "run_id": run_id,
            "site_id": site_id,
            "raw_name": raw_name,
        }

        if old is None:
            # A first sighting is one event or the other, never both: a preorder
            # opening is the more specific thing to say about it.
            events.append({
                **base,
                "event_type": (
                    "new_preorder" if new_availability == "preorder" else "new_listing"
                ),
                "old_value": None,
                "new_value": new_price_str,
            })
            continue

        old_price = old.get("latest_price")
        old_availability = old.get("availability") or "unknown"
        price_threshold = 1.0 if p.get("currency") == "SEK" else 0.01
        if (old_price is not None and new_price is not None
                and abs(new_price - old_price) >= price_threshold):
            # Direction is decided here rather than by a CAST in the UI query,
            # so the updates(event_type, created_at) index can do the filtering.
            events.append({
                **base,
                "event_type": "price_drop" if new_price < old_price else "price_rise",
                "old_value": str(old_price),
                "new_value": new_price_str,
            })

        transition = _TRANSITION_EVENTS.get((old_availability, new_availability))
        if transition == "new_preorder":
            # Same shape as a first-sighting preorder: the price is the payload,
            # so the operator can judge the preorder without opening the shop.
            events.append({
                **base,
                "event_type": transition,
                "old_value": None,
                "new_value": new_price_str,
            })
        elif transition == "back_in_stock":
            # The previous state rides along so a preorder going live on release
            # day is distinguishable from an ordinary restock.
            events.append({
                **base,
                "event_type": transition,
                "old_value": old_availability,
                "new_value": new_availability,
            })

    return events


def _scrape_source_url(
    conn: sqlite3.Connection,
    config: dict,
    site_id: int,
    run_id: int,
    source_url: str,
    sleep_first: bool,
    products_seen: list[dict],
    from_preorder_url: bool = False,
) -> int:
    """Scrape every page of one source URL, appending its products to products_seen.

    Returns the page count. Listings are upserted page by page, as they are read,
    and the caller owns products_seen so that a page that fails mid-pagination
    still leaves the earlier pages' products with it: those listings are already
    committed, so their events have to be written or the change is lost.

    sleep_first jitters before the very first fetch, which is how the inter-page
    sleep also lands between the source URLs of a multi-URL site.

    from_preorder_url says this URL came from the config's preorder_urls; it
    reaches both the parser (where it outranks every availability form) and the
    listings row (where the column records it for the event diff).
    """
    site_name = config.get("site_name", source_url)
    currency = _currency_for(source_url)
    urls = paginate(config, source_url)

    pages_fetched = 0
    page_counts: list[int] = []
    exhausted_pages = False
    previous_names: Optional[set] = None

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

        products = scrape_page(html, config, from_preorder_url=from_preorder_url)
        pages_fetched += 1

        if not products:
            logger.info("%s: empty page at %s, stopping pagination", site_name, url)
            exhausted_pages = True
            break

        names = {p["raw_name"] for p in products}
        if names == previous_names:
            # Some shops ignore the page parameter and serve page 1 again rather
            # than 404ing, so the only end-of-listing signal is the repeat.
            # Without this the run spends every remaining max_pages fetch on the
            # same products and then warns that max_pages is too low.
            logger.info(
                "%s: %s repeats the previous page, stopping pagination",
                site_name, url,
            )
            exhausted_pages = True
            break
        previous_names = names

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
                from_preorder_url=from_preorder_url,
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

    return pages_fetched


def run_site(
    config: dict, conn: sqlite3.Connection, run_id: Optional[int] = None
) -> None:
    """Scrape one site and persist its listings and the events they imply.

    A config may name one source URL ("source_url") or several ("source_urls"),
    plus any number of preorder category URLs ("preorder_urls"); each is
    paginated independently and all of them feed the same site identity.

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

        # _scrape_source_url commits its listings page by page, so a failure
        # partway through leaves the earlier pages' rows updated. The events go in
        # under `finally` for that reason: dropping them would leave the next run
        # diffing against those updated rows, and the price drop or restock in
        # between would never be reported at all.
        try:
            for i, (source_url, is_preorder) in enumerate(tagged_source_urls(config)):
                pages_fetched += _scrape_source_url(
                    conn, config, site_id, run_id, source_url, sleep_first=i > 0,
                    products_seen=all_products, from_preorder_url=is_preorder,
                )
            # Every source URL of the site came back, so a listing missing from
            # all of them really is missing. This has to stay inside the try and
            # out of the finally: a partial scrape must not sweep anything.
            _apply_absent_means(conn, config, site_id, all_products, pre_state)
        finally:
            # An empty pre_state is a brand-new site: record its catalogue silently.
            if all_products and pre_state:
                events = _build_update_events(site_id, run_id, all_products, pre_state)
                if events:
                    db.write_updates(conn, events)

        priced = _priced_name_count(all_products)
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
