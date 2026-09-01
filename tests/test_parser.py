"""Tests for detect_availability and scrape_page."""
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from scraper.parser import availability_forms, detect_availability, scrape_page


def make_el(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser").find()


# ── text_map ──────────────────────────────────────────────────────────────────

BADGE_CFG = {
    "availability": {
        "selector": "span.badge",
        "text_map": {
            "Varastossa": "in_stock",
            "Loppu": "out_of_stock",
            "Ennakkotilaus": "preorder",
        },
        "default": "unknown",
    }
}


def test_text_map_in_stock():
    el = make_el('<li><span class="badge">Varastossa</span></li>')
    assert detect_availability(el, BADGE_CFG) == ("in_stock", "Varastossa")


def test_text_map_out_of_stock():
    el = make_el('<li><span class="badge">Loppu</span></li>')
    assert detect_availability(el, BADGE_CFG) == ("out_of_stock", "Loppu")


def test_text_map_matches_as_substring_so_a_trailing_date_still_resolves():
    el = make_el('<li><span class="badge">Ennakkotilaus 12.9.2026</span></li>')
    availability, text = detect_availability(el, BADGE_CFG)
    assert availability == "preorder"
    assert text == "Ennakkotilaus 12.9.2026"


def test_text_map_is_case_and_whitespace_insensitive():
    el = make_el('<li><span class="badge">  ENNAKKO\n   TILAUS  </span></li>')
    cfg = {"availability": {"selector": "span.badge",
                            "text_map": {"ennakko tilaus": "preorder"}}}
    assert detect_availability(el, cfg)[0] == "preorder"


def test_text_map_prefers_the_longest_matching_key():
    """"Ei varastossa" must not resolve to in_stock via the shorter key."""
    el = make_el('<li><span class="badge">Ei varastossa</span></li>')
    cfg = {"availability": {"selector": "span.badge",
                            "text_map": {"varastossa": "in_stock",
                                         "ei varastossa": "out_of_stock"}}}
    assert detect_availability(el, cfg)[0] == "out_of_stock"


def test_text_map_checks_every_element_matching_the_selector():
    """prisma.fi's selector is `p`, and the badge is one of several."""
    el = make_el('<li><p>Tuotekuvaus</p><p>Ei saatavilla</p></li>')
    cfg = {"availability": {"selector": "p",
                            "text_map": {"Ei saatavilla": "out_of_stock"},
                            "default": "in_stock"}}
    assert detect_availability(el, cfg) == ("out_of_stock", "Ei saatavilla")


def test_text_map_prefers_the_longest_key_across_elements_not_within_one():
    """A shop printing two badges must not have document order beat key length.

    "Varastossa" comes first in the DOM, but "Ennakkotilaus 12.9.2026" is the
    longer key, so the item is a preorder rather than stock on the shelf.
    """
    el = make_el('<li><span class="badge">Varastossa</span>'
                 '<span class="badge">Ennakkotilaus 12.9.2026</span></li>')
    availability, text = detect_availability(el, BADGE_CFG)
    assert availability == "preorder"
    assert text == "Ennakkotilaus 12.9.2026"


def test_text_map_no_match_falls_through_to_default():
    el = make_el('<li><span class="badge">Uutuus</span></li>')
    cfg = {"availability": {"selector": "span.badge",
                            "text_map": {"Loppu": "out_of_stock"},
                            "default": "in_stock"}}
    assert detect_availability(el, cfg) == ("in_stock", None)


def test_text_map_without_a_selector_reads_the_container_text():
    el = make_el('<li>Loppuunmyyty</li>')
    cfg = {"availability": {"text_map": {"loppuunmyyty": "out_of_stock"}}}
    assert detect_availability(el, cfg) == ("out_of_stock", "Loppuunmyyty")


# ── presence ──────────────────────────────────────────────────────────────────

PRESENCE_CFG = {
    "availability": {
        "presence": {"selector": ".in-stock", "present": "in_stock",
                     "absent": "out_of_stock"}
    }
}


def test_presence_present_state():
    el = make_el('<li><span class="in-stock">Varastossa</span></li>')
    assert detect_availability(el, PRESENCE_CFG) == ("in_stock", "Varastossa")


def test_presence_absent_state():
    el = make_el('<li class="product"></li>')
    assert detect_availability(el, PRESENCE_CFG) == ("out_of_stock", None)


def test_presence_states_can_be_swapped_for_a_sold_out_marker():
    """The old `inverted` mode: the selector marks out of stock."""
    cfg = {"availability": {"presence": {"selector": ".sold-out",
                                         "present": "out_of_stock",
                                         "absent": "in_stock"}}}
    assert detect_availability(make_el('<li><i class="sold-out"></i></li>'), cfg)[0] == "out_of_stock"
    assert detect_availability(make_el('<li></li>'), cfg)[0] == "in_stock"


def test_presence_uses_its_own_selector_not_the_block_selector():
    el = make_el('<li><span class="badge">Uutuus</span><b class="cart">Osta</b></li>')
    cfg = {"availability": {"selector": "span.badge",
                            "presence": {"selector": "b.cart", "present": "in_stock",
                                         "absent": "out_of_stock"}}}
    assert detect_availability(el, cfg) == ("in_stock", "Osta")


def test_presence_falls_through_when_the_matching_state_is_not_configured():
    """A presence block with only `present` must not swallow the absent case."""
    cfg = {"availability": {"presence": {"selector": ".in-stock", "present": "in_stock"},
                            "default": "unknown"}}
    assert detect_availability(make_el('<li></li>'), cfg) == ("unknown", None)


# ── container_class_map ───────────────────────────────────────────────────────

CLASS_CFG = {
    "availability": {
        "container_class_map": {"instock": "in_stock", "outofstock": "out_of_stock",
                                "unavailable": "out_of_stock"}
    }
}


def test_container_class_map_instock():
    el = make_el('<li class="product instock">')
    assert detect_availability(el, CLASS_CFG) == ("in_stock", "product instock")


def test_container_class_map_outofstock():
    el = make_el('<li class="product outofstock">')
    assert detect_availability(el, CLASS_CFG) == ("out_of_stock", "product outofstock")


def test_container_class_map_unavailable():
    el = make_el('<li class="product-card unavailable">')
    assert detect_availability(el, CLASS_CFG)[0] == "out_of_stock"


def test_container_class_map_no_matching_class_falls_through_to_default():
    el = make_el('<li class="product">')
    assert detect_availability(el, CLASS_CFG) == ("unknown", None)


# ── attribute ─────────────────────────────────────────────────────────────────

ATTR_CFG = {
    "availability": {
        "selector": ".lipscore-rating-small",
        "attribute": {"name": "data-ls-availability",
                      "map": {"InStock": "in_stock", "OutOfStock": "out_of_stock",
                              "PreOrder": "preorder"}},
    }
}


@pytest.mark.parametrize("value,expected", [
    ("InStock", "in_stock"),
    ("OutOfStock", "out_of_stock"),
    ("PreOrder", "preorder"),
])
def test_attribute_maps_its_values(value, expected):
    el = make_el(f'<div><span class="lipscore-rating-small" data-ls-availability="{value}"></span></div>')
    assert detect_availability(el, ATTR_CFG) == (expected, value)


def test_attribute_value_outside_the_map_falls_through_to_default():
    el = make_el('<div><span class="lipscore-rating-small" data-ls-availability="Backorder"></span></div>')
    assert detect_availability(el, ATTR_CFG) == ("unknown", None)


def test_attribute_reads_the_container_when_the_block_has_no_selector():
    el = make_el('<li data-stock="OutOfStock"></li>')
    cfg = {"availability": {"attribute": {"name": "data-stock",
                                          "map": {"OutOfStock": "out_of_stock"}}}}
    assert detect_availability(el, cfg) == ("out_of_stock", "OutOfStock")


# ── precedence ────────────────────────────────────────────────────────────────

def test_text_map_beats_container_class_map():
    el = make_el('<li class="product instock"><span class="badge">Loppu</span></li>')
    cfg = {"availability": {
        "selector": "span.badge",
        "text_map": {"Loppu": "out_of_stock"},
        "container_class_map": {"instock": "in_stock"},
    }}
    assert detect_availability(el, cfg) == ("out_of_stock", "Loppu")


def test_presence_beats_container_class_map():
    el = make_el('<li class="product outofstock"><b class="cart">Osta</b></li>')
    cfg = {"availability": {
        "presence": {"selector": "b.cart", "present": "in_stock", "absent": "out_of_stock"},
        "container_class_map": {"outofstock": "out_of_stock"},
    }}
    assert detect_availability(el, cfg)[0] == "in_stock"


def test_container_class_map_beats_attribute():
    el = make_el('<li class="product instock" data-stock="OutOfStock"></li>')
    cfg = {"availability": {
        "container_class_map": {"instock": "in_stock"},
        "attribute": {"name": "data-stock", "map": {"OutOfStock": "out_of_stock"}},
    }}
    assert detect_availability(el, cfg)[0] == "in_stock"


def test_preorder_url_loses_to_a_real_badge():
    """A shop's preorder page can still list an item as sold out."""
    el = make_el('<li><span class="badge">Loppu</span></li>')
    availability, text = detect_availability(el, BADGE_CFG, from_preorder_url=True)
    assert (availability, text) == ("out_of_stock", "Loppu")


def test_preorder_url_wins_over_default():
    el = make_el('<li><span class="badge">Uutuus</span></li>')
    cfg = {"availability": {"selector": "span.badge",
                            "text_map": {"Loppu": "out_of_stock"},
                            "default": "in_stock"}}
    assert detect_availability(el, cfg, from_preorder_url=True) == ("preorder", "(preorder url)")


# ── no block, defaults, text cap ──────────────────────────────────────────────

def test_no_availability_block_is_unknown():
    el = make_el('<li class="product instock"><span class="badge">Varastossa</span></li>')
    assert detect_availability(el, {}) == ("unknown", None)


def test_no_availability_block_ignores_the_preorder_url_flag():
    """A site with no block reports untracked, not preorder-everything."""
    assert detect_availability(make_el('<li>'), {}, from_preorder_url=True) == ("unknown", None)


def test_default_defaults_to_unknown():
    el = make_el('<li><span class="badge">Uutuus</span></li>')
    cfg = {"availability": {"selector": "span.badge", "text_map": {"Loppu": "out_of_stock"}}}
    assert detect_availability(el, cfg) == ("unknown", None)


def test_availability_text_is_capped_at_120_chars():
    badge = "Ennakkotilaus " + "x" * 200
    el = make_el(f'<li><span class="badge">{badge}</span></li>')
    _, text = detect_availability(el, BADGE_CFG)
    assert len(text) == 120
    assert text == badge[:120]


# ── config states outside the allowed set ─────────────────────────────────────

BAD_STATE_CASES = [
    ({"selector": "span.badge", "text_map": {"Varastossa": "instock"}},
     '<li><span class="badge">Varastossa</span></li>'),
    ({"presence": {"selector": ".in-stock", "present": "in stock"}},
     '<li><span class="in-stock">Varastossa</span></li>'),
    ({"container_class_map": {"instock": "IN_STOCK"}},
     '<li class="product instock"></li>'),
    ({"attribute": {"name": "data-a", "map": {"InStock": "available"}}},
     '<li data-a="InStock"></li>'),
    ({"default": "in-stock"}, '<li></li>'),
]


@pytest.mark.parametrize("block,html", BAD_STATE_CASES)
def test_a_state_outside_the_allowed_set_reads_as_unknown(block, html, caplog):
    """A config typo must cost one listing, not the whole site.

    The state goes into a column with a CHECK constraint, so passing it through
    would raise on insert and run_site would log a site-wide failure.
    """
    cfg = {"site_name": "Testishop", "availability": block}
    with caplog.at_level("WARNING"):
        availability, _ = detect_availability(make_el(html), cfg)
    assert availability == "unknown"
    assert "Testishop" in caplog.text


# ── availability_forms (written to sites.availability_mode) ───────────────────

def test_availability_forms_lists_configured_forms_in_precedence_order():
    cfg = {"availability": {
        "attribute": {"name": "x", "map": {}},
        "text_map": {"a": "in_stock"},
        "container_class_map": {"instock": "in_stock"},
    }}
    assert availability_forms(cfg) == "text_map,container_class_map,attribute"


def test_availability_forms_is_none_without_a_block():
    assert availability_forms({}) is None


def test_availability_forms_is_none_when_the_block_configures_no_form():
    """A block that only sets a default tracks nothing, so it reads as untracked."""
    assert availability_forms({"availability": {"default": "unknown"}}) is None


# ── scrape_page: tcgkauppa.fi (WooCommerce container-class) ─────────────────

TCGKAUPPA_CFG = {
    "site_name": "TCG-kauppa",
    "currency": "EUR",
    "availability": {
        "container_class_map": {"instock": "in_stock", "outofstock": "out_of_stock",
                               "unavailable": "out_of_stock"},
    },
    "selectors": {
        "product_container": "li.product",
        "product_name": "h3.product-title a",
        "price": "span.price",
        "product_url": "h3.product-title a",
    },
}

def test_scrape_page_tcgkauppa_product_count():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    assert len(products) == 48

def test_scrape_page_tcgkauppa_has_names_and_prices():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    # All products should have a non-empty name
    assert all(p["raw_name"] for p in products)
    # All products should have a float price or None (suspicious price guard)
    assert all(isinstance(p["price"], float) or p["price"] is None for p in products)

def test_scrape_page_tcgkauppa_availability_from_container_class():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    in_stock = [p for p in products if p["availability"] == "in_stock"]
    out_stock = [p for p in products if p["availability"] == "out_of_stock"]
    assert len(in_stock) == 6
    assert len(out_stock) == 42
    assert all("instock" in p["availability_text"] for p in in_stock)

def test_scrape_page_tcgkauppa_currency():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    assert all(p["currency"] == "EUR" for p in products)


# ── scrape_page: peliparatiisi.net (Shopify Dawn inverted badge) ─────────────

PELIPARATIISI_CFG = {
    "site_name": "Peliparatiisi",
    "currency": "EUR",
    "availability": {
        "selector": ".badge",
        "text_map": {"Sold out": "out_of_stock"},
        "default": "in_stock",
    },
    "selectors": {
        "product_container": "li.grid__item",
        "product_name": "h3.card__heading.h5 a",
        "price": ".price-item--sale",
        "price_fallback": ".price-item--regular",
        "product_url": "h3.card__heading.h5 a",
    },
}

def test_scrape_page_peliparatiisi_product_count():
    html = Path("tests/fixtures/peliparatiisi.net/page1.html").read_text()
    products = scrape_page(html, PELIPARATIISI_CFG)
    assert len(products) == 16

def test_scrape_page_peliparatiisi_no_duplicate_names():
    """h3.card__heading.h5 selector must prevent double extraction."""
    html = Path("tests/fixtures/peliparatiisi.net/page1.html").read_text()
    products = scrape_page(html, PELIPARATIISI_CFG)
    names = [p["raw_name"] for p in products]
    assert len(names) == len(set(names)), "Duplicate product names found"

def test_scrape_page_peliparatiisi_availability_from_badge_text():
    html = Path("tests/fixtures/peliparatiisi.net/page1.html").read_text()
    products = scrape_page(html, PELIPARATIISI_CFG)
    sold_out = [p for p in products if p["availability"] == "out_of_stock"]
    in_stock = [p for p in products if p["availability"] == "in_stock"]
    assert len(sold_out) == 12
    assert len(in_stock) == 4
    assert sold_out[0]["availability_text"] == "Sold out"
    # The in-stock reading comes from the default, so there is no badge text.
    assert in_stock[0]["availability_text"] is None

def test_scrape_page_peliparatiisi_price_is_comma_decimal():
    """Prices from fixture must be comma-decimal values (e.g. 39.9 not 3990.0)."""
    html = Path("tests/fixtures/peliparatiisi.net/page1.html").read_text()
    products = scrape_page(html, PELIPARATIISI_CFG)
    prices = [p["price"] for p in products if p["price"] is not None]
    assert all(p <= 200.0 for p in prices), f"Suspiciously large price found: {max(prices)}"


# ── scrape_page: karkkainen.com (attribute-based price + stock) ──────────────

KARKKAINEN_CFG = {
    "site_name": "Karkkainen.com verkkokauppa",
    "currency": "EUR",
    "availability": {
        "selector": ".lipscore-rating-small",
        "attribute": {"name": "data-ls-availability",
                      "map": {"InStock": "in_stock", "OutOfStock": "out_of_stock",
                              "PreOrder": "preorder"}},
    },
    "selectors": {
        "product_container": '[data-testid="product-card-container"]',
        "product_name": '[data-testid="product-card-name-link"] p',
        "price": ".lipscore-rating-small",
        "product_url": '[data-testid="product-card-name-link"]',
    },
}

def test_scrape_page_karkkainen_reads_attribute_price():
    html = Path("tests/fixtures/karkkainen.com/page1.html").read_text()
    products = scrape_page(html, KARKKAINEN_CFG)
    assert len(products) > 0
    # First product price comes from data-ls-price attr (6.49)
    assert products[0]["price"] == 6.49

def test_attribute_price_honours_max_price_override():
    """The data-ls-price path shares parse_price's configurable ceiling."""
    html = '<li class="p"><span class="lipscore-rating-small" data-ls-price="2850.0"></span></li>'
    cfg = {"selectors": {"product_container": "li.p", "price": ".lipscore-rating-small"}}
    assert scrape_page(html, cfg)[0]["price"] is None
    assert scrape_page(html, {**cfg, "max_price": 5000.0})[0]["price"] == 2850.0

def test_itemprop_price_honours_the_suspicious_price_guard():
    """The itemprop="Price" path shares the same bounds as the text path."""
    cfg = {"selectors": {"product_container": "li.p", "price": ".pr"}}
    def price_for(content):
        html = f'<li class="p"><span class="pr" itemprop="Price" content="{content}"></span></li>'
        return scrape_page(html, cfg)[0]["price"]
    assert price_for("16.95") == 16.95
    assert price_for("0.01") is None
    assert price_for("1340453.94") is None

def test_itemprop_price_honours_max_price_override():
    cfg = {"selectors": {"product_container": "li.p", "price": ".pr"}, "max_price": 5000.0}
    html = '<li class="p"><span class="pr" itemprop="Price" content="2850.0"></span></li>'
    assert scrape_page(html, cfg)[0]["price"] == 2850.0

def test_scrape_page_karkkainen_reads_attribute_stock():
    html = Path("tests/fixtures/karkkainen.com/page1.html").read_text()
    products = scrape_page(html, KARKKAINEN_CFG)
    # All sampled items were OutOfStock in the fixture
    assert all(p["availability"] == "out_of_stock" for p in products)
    assert all(p["availability_text"] == "OutOfStock" for p in products)


# ── scrape_page: poromagia.com (product_line only, no product_pod) ───────────

POROMAGIA_CFG = {
    "site_name": "Poromagia",
    "currency": "EUR",
    "availability": {
        "presence": {"selector": ".instock.availability", "present": "in_stock",
                     "absent": "out_of_stock"},
    },
    "selectors": {
        "product_container": "article.product_line",
        "product_name": "h3 a",
        "price": ".price_color",
        "product_url": "h3 a",
    },
}

def test_scrape_page_poromagia_excludes_product_pod_widgets():
    html = Path("tests/fixtures/poromagia.com/page1.html").read_text()
    products = scrape_page(html, POROMAGIA_CFG)
    # product_line gives 20 per page; product_pod widget would add 6 duplicates
    assert len(products) == 20

def test_scrape_page_poromagia_names_and_prices():
    html = Path("tests/fixtures/poromagia.com/page1.html").read_text()
    products = scrape_page(html, POROMAGIA_CFG)
    assert all(p["raw_name"] for p in products)
    assert all(isinstance(p["price"], float) for p in products)


# ── scrape_page: prisma.fi (scoped ul to exclude carousel) ───────────────────

PRISMA_CFG = {
    "site_name": "Prisma.fi",
    "currency": "EUR",
    "availability": {
        "selector": "p",
        "text_map": {"Ei saatavilla": "out_of_stock"},
        "default": "in_stock",
    },
    "container_scope": "ul[data-test-id='brand-product-list']",
    "selectors": {
        "product_container": "li",
        "product_name": "a[data-test-id='product-card-link']",
        "price": "[data-test-id='product-card-price']",
        "product_url": "a[data-test-id='product-card-link']",
    },
}

def test_scrape_page_prisma_product_count():
    html = Path("tests/fixtures/prisma.fi/page1.html").read_text()
    products = scrape_page(html, PRISMA_CFG)
    assert len(products) == 33

def test_scrape_page_prisma_stock_ei_saatavilla():
    html = Path("tests/fixtures/prisma.fi/page1.html").read_text()
    products = scrape_page(html, PRISMA_CFG)
    out_of_stock = [p for p in products if p["availability"] == "out_of_stock"]
    assert len(out_of_stock) == 4


# ── scrape_page: spelparken.se (Shopify Dawn, SEK, badge_text stock) ─────────

SPELPARKEN_CFG = {
    "site_name": "Spelparken",
    "currency": "SEK",
    "availability": {
        "selector": ".card__badge .badge",
        "text_map": {"Slutsåld": "out_of_stock"},
        "default": "in_stock",
    },
    "selectors": {
        "product_container": "li.grid__item",
        "product_name": "h3.card__heading a",
        "price": ".price-item--sale",
        "price_fallback": ".price-item--regular",
        "product_url": "h3.card__heading a",
    },
}


def test_scrape_page_spelparken_sale_price_wins():
    """Discounted product should return the sale price, not the regular price."""
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    discounted = next(p for p in products if "Scarlet" in p["raw_name"])
    assert discounted["price"] == 849.0


def test_scrape_page_spelparken_regular_price_fallback():
    """Non-discounted product should return the regular price."""
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    regular = next(p for p in products if "Paldea" in p["raw_name"])
    assert regular["price"] == 1299.0


def test_scrape_page_spelparken_sold_out_detection():
    """Product with 'Slutsåld' badge should be out of stock."""
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    sold_out = [p for p in products if p["availability"] == "out_of_stock"]
    assert len(sold_out) == 1
    assert "Obsidian" in sold_out[0]["raw_name"]
    assert sold_out[0]["availability_text"] == "Slutsåld"


def test_scrape_page_spelparken_nyhet_badge_is_in_stock():
    """Product with 'Nyhet' badge must NOT be treated as out of stock."""
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    nyhet = next(p for p in products if "Twilight" in p["raw_name"])
    assert nyhet["availability"] == "in_stock"


def test_scrape_page_spelparken_currency_is_sek():
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    assert all(p["currency"] == "SEK" for p in products)


# ── product_url extraction: anchor-as-container (karukortti.fi) ────────────────

# Mirrors site_configs/karukortti.fi.json — product_url is null because the
# container itself is the <a>.
KARUKORTTI_CFG = {
    "site_name": "KaruKortti",
    "availability": {
        "presence": {"selector": ".product-sold-out-label",
                     "present": "out_of_stock", "absent": "in_stock"},
    },
    "selectors": {
        "product_container": 'a[data-selector="list-product-view"]',
        "product_name": '[data-selector="os-theme-product-list-name"]',
        "price": '[data-selector="os-theme-product-list-price-regular"]',
        "product_url": None,
    },
}


def test_scrape_page_karukortti_product_count():
    html = Path("tests/fixtures/karukortti.fi/page1.html").read_text()
    products = scrape_page(html, KARUKORTTI_CFG)
    assert len(products) == 8


def test_scrape_page_karukortti_every_product_has_a_url():
    """Container IS the anchor, so its own href is the product URL."""
    html = Path("tests/fixtures/karukortti.fi/page1.html").read_text()
    products = scrape_page(html, KARUKORTTI_CFG)
    assert all(p["product_url"] for p in products)
    assert all(
        p["product_url"].startswith("https://karukortti.fi/product/")
        for p in products
    )


def test_extract_url_container_href_may_be_relative():
    """The href is returned verbatim; runner._absolute_url resolves it."""
    html = '<div><a data-selector="list-product-view" href="/product/x">' \
           '<span data-selector="os-theme-product-list-name">X</span></a></div>'
    products = scrape_page(html, KARUKORTTI_CFG)
    assert products[0]["product_url"] == "/product/x"


def test_scrape_page_non_anchor_container_without_selector_has_no_url():
    """No product_url selector and a non-anchor container → empty, not garbage."""
    cfg = {
        "site_name": "Test",
        "selectors": {"product_container": "li.product", "product_name": "h3"},
    }
    html = '<ul><li class="product" href="/nope"><h3>Thing</h3></li></ul>'
    products = scrape_page(html, cfg)
    assert products[0]["product_url"] == ""
