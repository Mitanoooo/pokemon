"""Tests for scraper.discord.notify_matches and its per-page dispatch."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper import discord
from scraper.fetcher import FetchError
from scraper.runner import run_all_sites, run_site

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _cfg(name, source_url):
    return {
        "site_name": name,
        "source_url": source_url,
        "method": "css",
        "selectors": {
            "product_container": "li.product",
            "product_name": "h2",
            "price": ".price",
            "product_url": "a",
        },
        "pagination": {"type": "none", "max_pages": 1},
    }


def _listing(name, price=9.99):
    return {"raw_name": name, "price": price, "currency": "EUR",
            "availability": "in_stock", "product_url": ""}


def _seed_event(conn, site_name, raw_name, event_type="new_listing"):
    """Insert a site and one update for it, returning the update's row id."""
    site_id = conn.execute(
        "INSERT INTO sites (url, name) VALUES (?, ?)",
        (f"https://{site_name}/", site_name),
    ).lastrowid
    update_id = conn.execute(
        "INSERT INTO updates (run_id, site_id, raw_name, event_type) VALUES (1, ?, ?, ?)",
        (site_id, raw_name, event_type),
    ).lastrowid
    conn.commit()
    return update_id


def _posted_bodies(post):
    return [c.kwargs["json"]["content"] for c in post.call_args_list]


def test_notify_matches_posts_only_the_given_update_ids(conn):
    alerted = _seed_event(conn, "shop-a", "Booster Box")
    _seed_event(conn, "shop-b", "Booster Box")
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.commit()

    with patch("scraper.discord.requests.post") as post:
        discord.notify_matches(conn, "https://hook", [alerted])

    assert post.call_count == 1
    body = _posted_bodies(post)[0]
    assert "shop-a" in body
    assert "shop-b" not in body


def test_notify_matches_batches_every_given_id_into_one_message(conn):
    ids = [
        _seed_event(conn, "shop-a", "Booster Box"),
        _seed_event(conn, "shop-b", "Booster Box"),
    ]
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.commit()

    with patch("scraper.discord.requests.post") as post:
        discord.notify_matches(conn, "https://hook", ids)

    assert post.call_count == 1
    body = _posted_bodies(post)[0]
    assert "shop-a" in body and "shop-b" in body


def test_notify_matches_with_no_ids_does_not_post(conn):
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.commit()

    with patch("scraper.discord.requests.post") as post:
        discord.notify_matches(conn, "https://hook", [])

    assert post.call_count == 0


def test_run_site_posts_its_matches_before_returning(conn):
    cfg = _cfg("Shop A", "https://shop-a.fi/")
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[_listing("Old Box")]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.commit()

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page",
               return_value=[_listing("Old Box"), _listing("Booster Box")]), \
         patch("scraper.runner.time.sleep"), \
         patch("scraper.discord.requests.post") as post:
        run_site(cfg, conn, discord_webhook_url="https://hook")

    assert post.call_count == 1
    assert "Booster Box" in _posted_bodies(post)[0]


def test_run_site_notification_failure_does_not_mark_the_site_unhealthy(conn):
    cfg = _cfg("Shop A", "https://shop-a.fi/")
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[_listing("Old Box")]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.commit()

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page",
               return_value=[_listing("Old Box"), _listing("Booster Box")]), \
         patch("scraper.runner.time.sleep"), \
         patch("scraper.discord.notify_matches", side_effect=RuntimeError("hook down")):
        run_site(cfg, conn, discord_webhook_url="https://hook")

    site = conn.execute("SELECT * FROM sites WHERE name='Shop A'").fetchone()
    assert site["consecutive_failures"] == 0
    assert site["last_error"] is None


def _paged_cfg(name, source_url, max_pages):
    cfg = _cfg(name, source_url)
    cfg["pagination"] = {
        "type": "url_pattern",
        "url_pattern": "?page={page}",
        "max_pages": max_pages,
    }
    return cfg


def test_run_site_posts_a_match_before_fetching_the_next_page(conn):
    """The alert must not wait for the pages queued behind the hit."""
    cfg = _paged_cfg("Shop A", "https://shop-a.fi/", 3)
    pages = [
        [_listing("Page One Box")],
        [_listing("Booster Box")],
        [_listing("Page Three Box")],
    ]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=list(pages)), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    conn.execute("UPDATE listings SET latest_price = 20.00")
    conn.commit()

    events = []

    def record_fetch(url, *args, **kwargs):
        events.append(f"fetch {url}")
        return "<html>ok</html>"

    def record_post(url, **kwargs):
        events.append("post " + kwargs["json"]["content"].replace("\n", " "))
        return MagicMock()

    with patch("scraper.runner.fetch", side_effect=record_fetch), \
         patch("scraper.runner.scrape_page", side_effect=list(pages)), \
         patch("scraper.runner.time.sleep"), \
         patch("scraper.discord.requests.post", side_effect=record_post):
        run_site(cfg, conn, discord_webhook_url="https://hook")

    posts = [e for e in events if e.startswith("post ")]
    assert len(posts) == 1, events
    assert "Booster Box" in posts[0]
    assert events.index(posts[0]) < events.index("fetch https://shop-a.fi/?page=3")


def test_run_site_reports_a_repeated_listing_once(conn):
    """A product in two categories is alerted on the first page that carries it."""
    cfg = _paged_cfg("Shop A", "https://shop-a.fi/", 2)
    pages = [[_listing("Old Box")], [_listing("Old Box")]]
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=[[_listing("Filler")]]), \
         patch("scraper.runner.time.sleep"):
        run_site(_cfg("Shop A", "https://shop-a.fi/"), conn)
    conn.execute("INSERT INTO watch_keywords (keyword) VALUES ('box')")
    conn.commit()

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=list(pages)), \
         patch("scraper.runner.time.sleep"), \
         patch("scraper.discord.requests.post") as post:
        run_site(cfg, conn, discord_webhook_url="https://hook")

    assert post.call_count == 1
    assert _posted_bodies(post)[0].count("Old Box") == 1
    rows = conn.execute(
        "SELECT COUNT(*) FROM updates WHERE raw_name = 'Old Box'"
    ).fetchone()[0]
    assert rows == 1


def test_run_site_keeps_the_events_of_pages_read_before_a_failure(conn):
    cfg = _paged_cfg("Shop A", "https://shop-a.fi/", 2)
    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", side_effect=[[_listing("Old Box")]]), \
         patch("scraper.runner.time.sleep"):
        run_site(_cfg("Shop A", "https://shop-a.fi/"), conn)

    def fail_on_page_two(url, *args, **kwargs):
        if "page=2" in url:
            raise FetchError("500 on page 2", status_code=500)
        return "<html>ok</html>"

    with patch("scraper.runner.fetch", side_effect=fail_on_page_two), \
         patch("scraper.runner.scrape_page",
               side_effect=[[_listing("Old Box", price=5.00)]]), \
         patch("scraper.runner.time.sleep"):
        run_site(cfg, conn)

    row = conn.execute(
        "SELECT event_type FROM updates WHERE raw_name = 'Old Box'"
    ).fetchone()
    assert row["event_type"] == "price_drop"


def test_run_all_sites_posts_each_sites_alert_as_that_site_finishes(tmp_path):
    """An alert must not wait for the sites queued behind it."""
    db_path = str(tmp_path / "t.db")
    c = sqlite3.connect(db_path)
    c.executescript(SCHEMA)
    c.commit()

    configs_dir = tmp_path / "site_configs"
    configs_dir.mkdir()
    for name, host in [("a", "shop-a.fi"), ("b", "shop-b.fi")]:
        (configs_dir / f"{host}.json").write_text(
            json.dumps(_cfg(f"Shop {name.upper()}", f"https://{host}/"))
        )

    with patch("scraper.runner.fetch", return_value="<html>ok</html>"), \
         patch("scraper.runner.scrape_page", return_value=[_listing("Old Box")]), \
         patch("scraper.runner.time.sleep"):
        run_all_sites(db_path, configs_dir=str(configs_dir))

    c.execute("INSERT INTO watch_keywords (keyword) VALUES ('booster')")
    c.commit()

    events = []

    def record_fetch(url, *args, **kwargs):
        events.append(f"fetch {url}")
        return "<html>ok</html>"

    def record_post(url, **kwargs):
        events.append("post " + kwargs["json"]["content"].replace("\n", " "))
        return MagicMock()

    with patch("scraper.runner.fetch", side_effect=record_fetch), \
         patch("scraper.runner.scrape_page",
               return_value=[_listing("Old Box"), _listing("Booster Box")]), \
         patch("scraper.runner.time.sleep"), \
         patch("scraper.discord.requests.post", side_effect=record_post):
        run_all_sites(db_path, configs_dir=str(configs_dir),
                      discord_webhook_url="https://hook")

    posts = [e for e in events if e.startswith("post ")]
    assert len(posts) == 2, events
    # Shop A's alert goes out before Shop B is even fetched.
    assert events.index(posts[0]) < events.index("fetch https://shop-b.fi/")
    assert "Shop A" in posts[0] and "Shop B" in posts[1]
