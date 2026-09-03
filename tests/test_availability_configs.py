"""Guards for the availability blocks of ticket 18 that were not obvious.

Most sites print one badge per state and ticket 15's parser tests already cover
that shape. The sites here needed a reading of the live markup to get right, and
each fixture is a saved page cut down to a few product cards per state:

- blockhousegames.net: the inventory element is present on sold-out cards too,
  so a presence check read them as in stock.
- fantasialinna.com, lelupartanen.fi, maxgaming.fi: the state is free text, and
  maxgaming.fi is the only site printing all of in stock, sold out and preorder.
- kodintavaratalo.fi: the Pokemon listing is all in stock, so the sold-out
  branch is only exercised by another category (LEGO).
- pelimies.fi: a preorder tag beats the add-to-cart button that decides the rest.
- swagykarp.fi: preorder cards print "Pre order" in the same element sold-out
  cards print "Out of Stock" in, and only the first is mapped, on purpose.
- prisma.fi, karkkainen.com: the earlier blocks were silently wrong. Both read a
  full listing-page fixture (prisma page1.html, karkkainen facets.html) rather
  than a hand-cut one.
"""
import json
from collections import Counter
from pathlib import Path

import pytest

from scraper.parser import availability_forms, scrape_page

CONFIG_DIR = Path(__file__).parent.parent / "site_configs"
FIXTURE_DIR = Path(__file__).parent / "fixtures"

# (site, fixture file, expected state counts)
SPLITS = [
    ("blockhousegames.net", "availability.html", {"in_stock": 4, "out_of_stock": 4}),
    ("fantasialinna.com", "availability.html", {"in_stock": 4, "out_of_stock": 2}),
    ("kodintavaratalo.fi", "availability.html", {"in_stock": 4, "out_of_stock": 4}),
    ("lelupartanen.fi", "availability.html", {"in_stock": 4, "out_of_stock": 4}),
    ("maxgaming.fi", "availability.html", {"in_stock": 4, "out_of_stock": 4, "preorder": 4}),
    ("pelimies.fi", "availability.html", {"in_stock": 4, "preorder": 4}),
    ("swagykarp.fi", "availability.html", {"in_stock": 3, "out_of_stock": 2, "preorder": 2}),
    ("prisma.fi", "page1.html", {"in_stock": 29, "out_of_stock": 4}),
]


def _read(site, fixture):
    config = json.loads((CONFIG_DIR / f"{site}.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / site / fixture).read_text(encoding="utf-8")
    return scrape_page(html, config)


@pytest.mark.parametrize("site,fixture,expected", SPLITS)
def test_availability_split_on_the_saved_page(site, fixture, expected):
    """No expected split holds an unknown count: an unknown reading on a
    configured site means the block missed a wording the page prints."""
    products = _read(site, fixture)
    assert dict(Counter(p["availability"] for p in products)) == expected


def test_swagykarp_preorder_beats_its_own_out_of_stock_text():
    """Both texts live in .acoplw-blockText, and "Out of Stock" is the longer
    key, so mapping it as well would resolve preorder cards to out of stock."""
    products = _read("swagykarp.fi", "availability.html")
    preorders = [p for p in products if p["availability"] == "preorder"]
    assert preorders
    assert all(p["availability_text"] == "Pre order" for p in preorders)


def test_swagykarp_out_of_stock_comes_from_the_container_class():
    products = _read("swagykarp.fi", "availability.html")
    sold_out = [p for p in products if p["availability"] == "out_of_stock"]
    assert sold_out
    assert all(p["availability_text"] == "outofstock" for p in sold_out)


def test_maxgaming_reads_both_of_its_sold_out_wordings():
    products = _read("maxgaming.fi", "availability.html")
    texts = {p["availability_text"] for p in products if p["availability"] == "out_of_stock"}
    assert texts == {"Loppuunmyyty", "Loppu varastosta"}


def test_pelimies_preorder_tag_wins_over_the_add_to_cart_button():
    """Preorder cards carry a cart button as well, so presence alone would read
    every one of them as in stock."""
    products = _read("pelimies.fi", "availability.html")
    preorders = [p for p in products if p["availability"] == "preorder"]
    assert preorders
    assert all(p["availability_text"] == "Tuleva julkaisu" for p in preorders)


def test_blockhousegames_sold_out_cards_still_carry_the_inventory_element():
    """The reason this site needs a text_map: the element a presence check would
    look for is on the sold-out cards too."""
    products = _read("blockhousegames.net", "availability.html")
    sold_out = [p for p in products if p["availability"] == "out_of_stock"]
    assert all(p["availability_text"] == "Loppuunmyyty" for p in sold_out)


def test_prisma_does_not_read_its_whole_page_as_in_stock():
    """The old text_map selector was '.background-error p', which matched
    nothing, so every listing fell through to the in_stock default."""
    products = _read("prisma.fi", "page1.html")
    sold_out = [p for p in products if p["availability"] == "out_of_stock"]
    assert sold_out
    assert all(p["availability_text"] == "Ei saatavilla" for p in sold_out)


def test_karkkainen_reads_its_stock_filtered_page_as_in_stock():
    """data-ls-availability says OutOfStock on every card, including items its own
    product pages sell, so the config carries no form. The source URL instead
    facets on 'Saatavuus myyjältä: Kärkkäinen', so everything listed is in stock
    and dropping off the page is the shop's only out-of-stock signal."""
    config = json.loads((CONFIG_DIR / "karkkainen.com.json").read_text(encoding="utf-8"))
    assert availability_forms(config) == "absent"
    html = (FIXTURE_DIR / "karkkainen.com" / "facets.html").read_text(encoding="utf-8")
    products = scrape_page(html, config)
    assert products
    assert all(p["availability"] == "in_stock" for p in products)


def test_karkkainen_facets_keep_the_page_to_pokemon():
    """The bare Keräilykortit category carried 56 products, only 12 of them
    Pokemon; the rest were Lorcana, Magic, Panini and Topps tracked as Pokemon."""
    config = json.loads((CONFIG_DIR / "karkkainen.com.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / "karkkainen.com" / "facets.html").read_text(encoding="utf-8")
    names = [p["raw_name"].lower() for p in scrape_page(html, config)]
    assert names
    assert all("pokemon" in n or "pokémon" in n for n in names)
