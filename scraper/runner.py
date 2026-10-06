import glob
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import sqlite3

from scraper import db, discord as _discord
from scraper.fetcher import FetchError, fetch
from scraper.paginator import (
    is_paginated,
    paginate,
    source_urls,
    tagged_source_urls,
)
from scraper.parser import (
    AVAILABILITY_STATES,
    availability_forms,
    detail_availability,
    scrape_page,
)

logger = logging.getLogger(__name__)


def _currency_for(source_url: str) -> str:
    host = urlparse(source_url).hostname or ""
    return "SEK" if host.endswith(".se") else "EUR"


def _upsert_site(conn: sqlite3.Connection, config: dict) -> int:
    # A multi-URL config is still one site: its first source URL identifies it.
    # Identity is the site_name, not the url — url changes when a config gets
    # repointed, and matching on it orphaned the old row instead of updating it.
    url = source_urls(config)[0]
    name = config["site_name"]
    row = conn.execute("SELECT id, url FROM sites WHERE name = ?", (name,)).fetchone()
    if row:
        site_id, existing_url = row
        if existing_url != url:
            conn.execute("UPDATE sites SET url = ? WHERE id = ?", (url, site_id))
            conn.commit()
        return site_id
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
    # Last occurrence of each raw_name in this batch wins
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


class _EventReporter:
    """Writes the events one page implies and alerts on them straight away.

    One instance per site per run. The diff runs per page instead of once the
    site's last page is in, so a keyword hit reaches Discord while the remaining
    pages and source URLs are still being fetched. It also means the events of a
    scrape that fails halfway are already committed.

    The first page a raw_name appears on is the one that gets diffed; a later
    page repeating it is dropped, so a product listed in two categories is
    reported once, as early as it was seen. For that to be the right sighting,
    the caller must not hand over one the run goes on to overwrite — which is
    what the preorder claim in _scrape_source_url is for.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        site_id: int,
        run_id: int,
        pre_state: dict,
        webhook_url: str,
    ) -> None:
        self._conn = conn
        self._site_id = site_id
        self._run_id = run_id
        self._pre_state = pre_state
        self._webhook_url = webhook_url
        self._reported: set[str] = set()

    def report(self, products: list[dict]) -> None:
        # An empty pre_state is a brand-new site: record its catalogue silently.
        if not self._pre_state:
            return

        fresh = [p for p in products if p["raw_name"] not in self._reported]
        if not fresh:
            return
        self._reported.update(p["raw_name"] for p in fresh)

        events = _build_update_events(
            self._site_id, self._run_id, fresh, self._pre_state
        )
        if not events:
            return
        update_ids = db.write_updates(self._conn, events)
        self._notify(update_ids)

    def _notify(self, update_ids: list[int]) -> None:
        if not self._webhook_url:
            return
        try:
            _discord.notify_matches(self._conn, self._webhook_url, update_ids)
        except Exception as exc:
            # A dead webhook must not abort the scrape or be recorded as the
            # site's last_error.
            logger.warning(
                "Discord notification failed for site %d: %s", self._site_id, exc
            )


def _apply_detail_availability(
    products: list[dict], source_url: str, config: dict
) -> None:
    """Replace each product's availability with what its own page says.

    For configs with an `availability.detail` block, where the listing cards
    carry no stock signal. One request per product, jittered like pagination. A
    product whose page cannot be fetched reads unknown: no transition fires from
    or to unknown, so a failed fetch never reports a restock.
    """
    if not (config.get("availability") or {}).get("detail"):
        return

    site_name = config.get("site_name", source_url)
    for p in products:
        url = _absolute_url(source_url, p.get("product_url"))
        p["availability"], p["availability_text"] = "unknown", None
        if not url:
            continue
        time.sleep(random.uniform(1, 4))
        try:
            html = fetch(url, config)
        except FetchError as exc:
            logger.warning("%s: detail page failed, reading unknown: %s", site_name, exc)
            continue
        p["availability"], p["availability_text"] = detail_availability(html, config)


def _scrape_source_url(
    conn: sqlite3.Connection,
    config: dict,
    site_id: int,
    run_id: int,
    source_url: str,
    sleep_first: bool,
    products_seen: list[dict],
    reporter: _EventReporter,
    preorder_claims: set,
    from_preorder_url: bool = False,
) -> int:
    """Scrape every page of one source URL, appending its products to products_seen.

    Returns the page count. Listings are upserted and their events reported page
    by page, as they are read, so an alert goes out as soon as the product is
    seen and a page that fails mid-pagination leaves the earlier pages' work
    committed. The caller owns products_seen, which the site-wide checks
    (absent_means, health) need once every page is in.

    sleep_first jitters before the very first fetch, which is how the inter-page
    sleep also lands between the source URLs of a multi-URL site.

    from_preorder_url says this URL came from the config's preorder_urls; it
    reaches both the parser (where it outranks every availability form) and the
    listings row (where the column records it for the event diff).

    preorder_claims is shared across the site's source URLs for the whole run;
    see the claim comment below.
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
            html = fetch(url, config)
        else:
            # Past page 1, a 404 is how WooCommerce and friends say "no such
            # page" — the listing simply ended before max_pages. Anything else
            # (403, 500, a timeout) is a real failure and propagates.
            try:
                html = fetch(url, config)
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

        # A preorder sighting claims the name for the rest of the run, and a
        # normal collection listing the same product is then ignored: the shop
        # badges it in stock there (you can order it), and taking that sighting
        # would both overwrite the preorder row and report a restock. Claiming is
        # what makes this survive a partial scrape — the sighting that wins does
        # not depend on a later page arriving.
        if from_preorder_url:
            preorder_claims.update(p["raw_name"] for p in products)
            unclaimed = products
        else:
            unclaimed = [p for p in products if p["raw_name"] not in preorder_claims]

        if not from_preorder_url:
            _apply_detail_availability(unclaimed, source_url, config)

        # Every sighting lands in listings — including price-less ones, so
        # they do not look brand new next run. This must stay ahead of the
        # valid-price filter in run_site.
        for p in unclaimed:
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

        # After the upserts: the alert reads the product's price and URL off the
        # listing row the sighting just wrote.
        reporter.report(unclaimed)

        products_seen.extend(unclaimed)

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
    config: dict,
    conn: sqlite3.Connection,
    run_id: Optional[int] = None,
    discord_webhook_url: str = "",
) -> None:
    """Scrape one site and persist its listings and the events they imply.

    A config may name one source URL ("source_url") or several ("source_urls"),
    plus any number of preorder category URLs ("preorder_urls"); each is
    paginated independently and all of them feed the same site identity.

    run_id is normally supplied by run_all_sites() so every site in one batch
    shares a run. When called standalone it opens (and closes) its own run.

    With discord_webhook_url set, a matching event goes out on the page it was
    found on, without waiting for the site's remaining pages or the batch.
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
        # Snapshot state before this run's upserts for event diffing: every page's
        # diff is against the state the site was in when the run started.
        pre_state = db.get_listing_state(conn, site_id)
        reporter = _EventReporter(
            conn, site_id, run_id, pre_state, discord_webhook_url
        )

        preorder_claims: set = set()
        for i, (source_url, is_preorder) in enumerate(tagged_source_urls(config)):
            pages_fetched += _scrape_source_url(
                conn, config, site_id, run_id, source_url, sleep_first=i > 0,
                products_seen=all_products, reporter=reporter,
                preorder_claims=preorder_claims, from_preorder_url=is_preorder,
            )
        # Every source URL of the site came back, so a listing missing from all of
        # them really is missing. A partial scrape must not sweep anything, which
        # is why this sits after the loop rather than in a finally.
        _apply_absent_means(conn, config, site_id, all_products, pre_state)

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
    discord_webhook_url: str = "",
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

            every_n = config.get("scrape_every_n_runs")
            if every_n and run_id % every_n != 0:
                logger.debug(
                    "Skipping %s this run (scrape_every_n_runs=%d, run_id=%d)",
                    config.get("site_name", path), every_n, run_id,
                )
                continue

            run_site(config, conn, run_id=run_id,
                     discord_webhook_url=discord_webhook_url)
    finally:
        db.prune_updates(conn)
        db.finish_run(conn, run_id)
