"""Regression guards for the four sites of issue 04.

Keräilykortti.fi, Porvoon Pelikauppa, Proshop and Spelparken had never
produced a price at all: the pre-fix runner handed price-less products straight
to the writer, and a single unpriced card broke the insert for the whole site's
sightings that run.

These tests run each site's *real* config file against a saved page and assert
it still yields priced products, so a future selector edit cannot quietly take
a site back to zero.
"""
import json
from pathlib import Path

import pytest

from scraper.parser import scrape_page

CONFIG_DIR = Path(__file__).parent.parent / "site_configs"
FIXTURE_DIR = Path(__file__).parent / "fixtures"

# (config file, minimum priced products expected on the saved page)
RECOVERED_SITES = [
    ("kerailykortti.fi", 12),
    ("porvoonpelikauppa.fi", 18),
    ("proshop.fi", 16),
    ("spelparken.se", 4),
]


def _load(site: str) -> tuple[dict, str]:
    config = json.loads((CONFIG_DIR / f"{site}.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / site / "page1.html").read_text(encoding="utf-8")
    return config, html


@pytest.mark.parametrize("site,min_priced", RECOVERED_SITES)
def test_recovered_site_yields_priced_readings(site, min_priced):
    config, html = _load(site)
    products = scrape_page(html, config)
    priced = [p for p in products if p["price"] is not None]
    assert len(priced) >= min_priced, (
        f"{site}: only {len(priced)} of {len(products)} products priced"
    )


@pytest.mark.parametrize("site,_", RECOVERED_SITES)
def test_recovered_site_products_have_names(site, _):
    config, html = _load(site)
    assert all(p["raw_name"] for p in scrape_page(html, config))


@pytest.mark.parametrize("site,_", RECOVERED_SITES)
def test_recovered_site_products_have_urls(site, _):
    config, html = _load(site)
    assert all(p["product_url"] for p in scrape_page(html, config))


def test_porvoo_factory_case_price_survives_the_raised_ceiling():
    """The tehdaslaatikko prices are why porvoonpelikauppa.fi sets max_price."""
    config, html = _load("porvoonpelikauppa.fi")
    prices = [p["price"] for p in scrape_page(html, config) if p["price"] is not None]
    assert max(prices) > 2000.0


def test_porvoo_placeholder_price_is_still_rejected():
    """Raising max_price must not admit the 1,00 € pre-order placeholder."""
    config, html = _load("porvoonpelikauppa.fi")
    prices = [p["price"] for p in scrape_page(html, config) if p["price"] is not None]
    assert min(prices) >= 2.0


def test_proshop_demo_placeholder_price_is_rejected():
    """Proshop's *DEMO* item lists 1 340 453,94 € — the guard must drop it."""
    config, html = _load("proshop.fi")
    demo = next(p for p in scrape_page(html, config) if "*DEMO*" in p["raw_name"])
    assert demo["price"] is None
