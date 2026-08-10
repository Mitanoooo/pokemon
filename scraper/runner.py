import glob
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urlparse

import sqlite3

from scraper import db
from scraper.fetcher import fetch
from scraper.paginator import paginate
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


def run_site(config: dict, conn: sqlite3.Connection) -> None:
    site_name = config.get("site_name", config["source_url"])
    site_id = _upsert_site(conn, config)
    currency = _currency_for(config["source_url"])

    null_price_count = 0
    try:
        urls = paginate(config)
        all_readings: list[dict] = []
        pages_fetched = 0

        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(random.uniform(1, 4))

            html = fetch(url)
            if html is None:
                raise RuntimeError(f"fetch returned None for {url}")

            products = scrape_page(html, config)
            pages_fetched += 1

            if not products:
                logger.info("%s: empty page at %s, stopping pagination", site_name, url)
                break

            for p in products:
                p["currency"] = currency

            valid = [p for p in products if p.get("price") is not None]
            skipped = len(products) - len(valid)
            if skipped:
                null_price_count += skipped
                logger.warning(
                    "%s: skipped %d product(s) with no parseable price on %s",
                    site_name, skipped, url,
                )
            all_readings.extend(valid)

        if not all_readings:
            msg = "0 products across all pages"
            logger.warning("%s: pages=%d products=0 — %s", site_name, pages_fetched, msg)
            db.update_site_health(conn, site_id, success=False, error_text=msg,
                                  null_price_count=null_price_count)
            return

        db.write_readings(conn, site_id, all_readings)
        db.update_site_health(conn, site_id, success=True, null_price_count=null_price_count)
        logger.info("%s: pages=%d products=%d", site_name, pages_fetched, len(all_readings))

    except Exception as exc:
        error_text = str(exc)
        logger.error("%s: error — %s", site_name, error_text)
        db.update_site_health(conn, site_id, success=False, error_text=error_text,
                              null_price_count=null_price_count)


def run_all_sites(
    db_path: str,
    configs_dir: str = "site_configs",
) -> None:
    conn = db.get_connection(db_path)
    pattern = f"{configs_dir}/*.json"
    config_files = sorted(glob.glob(pattern))

    if not config_files:
        logger.warning("No site config files found in %s", configs_dir)

    for path in config_files:
        try:
            config = json.loads(open(path).read())
        except Exception as exc:
            logger.error("Failed to load config %s: %s", path, exc)
            continue

        if config.get("disabled"):
            logger.debug("Skipping disabled site: %s", config.get("site_name", path))
            continue

        run_site(config, conn)
