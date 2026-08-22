"""Tests for detect_stock and scrape_page."""
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from scraper.parser import detect_stock, scrape_page


# ── detect_stock helpers ─────────────────────────────────────────────────────

def make_el(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser").find()


# ── normal mode ──────────────────────────────────────────────────────────────

def test_detect_stock_normal_present():
    el = make_el('<li class="product"><span class="in-stock"></span></li>')
    assert detect_stock(el, {"stock_mode": "normal", "selectors": {"in_stock": ".in-stock"}}) is True

def test_detect_stock_normal_absent():
    el = make_el('<li class="product"></li>')
    assert detect_stock(el, {"stock_mode": "normal", "selectors": {"in_stock": ".in-stock"}}) is False


# ── inverted mode ────────────────────────────────────────────────────────────

def test_detect_stock_inverted_selector_absent_means_in_stock():
    el = make_el('<li class="product"></li>')
    assert detect_stock(el, {"stock_mode": "inverted", "selectors": {"in_stock": ".label--subdued"}}) is True

def test_detect_stock_inverted_selector_present_means_out_of_stock():
    el = make_el('<li class="product"><span class="label--subdued"></span></li>')
    assert detect_stock(el, {"stock_mode": "inverted", "selectors": {"in_stock": ".label--subdued"}}) is False


# ── badge_text mode ───────────────────────────────────────────────────────────

def test_detect_stock_badge_text_sold_out():
    el = make_el('<li><span class="badge">Sold out</span></li>')
    cfg = {"stock_mode": "badge_text", "selectors": {"in_stock": ".badge"}, "stock_badge_text": "Sold out"}
    assert detect_stock(el, cfg) is False

def test_detect_stock_badge_text_loppunut():
    el = make_el('<li><span class="product-badge-content">Loppunut</span></li>')
    cfg = {"stock_mode": "badge_text", "selectors": {"in_stock": ".product-badge-content"}, "stock_badge_text": "Loppunut"}
    assert detect_stock(el, cfg) is False

def test_detect_stock_badge_text_absent_means_in_stock():
    el = make_el('<li></li>')
    cfg = {"stock_mode": "badge_text", "selectors": {"in_stock": ".badge"}, "stock_badge_text": "Sold out"}
    assert detect_stock(el, cfg) is True

def test_detect_stock_badge_text_different_text_means_in_stock():
    # badge exists but says "New" not "Sold out" → still in stock
    el = make_el('<li><span class="badge">New</span></li>')
    cfg = {"stock_mode": "badge_text", "selectors": {"in_stock": ".badge"}, "stock_badge_text": "Sold out"}
    assert detect_stock(el, cfg) is True


# ── container_class mode ──────────────────────────────────────────────────────

def test_detect_stock_container_class_instock():
    el = make_el('<li class="product instock">')
    assert detect_stock(el, {"stock_mode": "container_class"}) is True

def test_detect_stock_container_class_outofstock():
    el = make_el('<li class="product outofstock">')
    assert detect_stock(el, {"stock_mode": "container_class"}) is False

def test_detect_stock_container_class_unavailable():
    # pbcards.fi uses "unavailable"
    el = make_el('<li class="product-card unavailable">')
    assert detect_stock(el, {"stock_mode": "container_class"}) is False


# ── attribute mode (karkkainen.com) ──────────────────────────────────────────

def test_detect_stock_attribute_instock():
    el = make_el('<div data-testid="product-card-container"><span class="lipscore-rating-small" data-ls-availability="InStock"></span></div>')
    assert detect_stock(el, {"stock_mode": "attribute", "selectors": {"in_stock": ".lipscore-rating-small"}}) is True

def test_detect_stock_attribute_outofstock():
    el = make_el('<div data-testid="product-card-container"><span class="lipscore-rating-small" data-ls-availability="OutOfStock"></span></div>')
    assert detect_stock(el, {"stock_mode": "attribute", "selectors": {"in_stock": ".lipscore-rating-small"}}) is False


# ── unknown / null mode ───────────────────────────────────────────────────────

def test_detect_stock_null_returns_none():
    el = make_el('<li class="product">')
    assert detect_stock(el, {"stock_mode": None}) is None

def test_detect_stock_unknown_returns_none():
    el = make_el('<li class="product">')
    assert detect_stock(el, {"stock_mode": "unknown"}) is None


# ── scrape_page: tcgkauppa.fi (WooCommerce container-class) ─────────────────

TCGKAUPPA_CFG = {
    "site_name": "TCG-kauppa",
    "currency": "EUR",
    "stock_mode": "container_class",
    "selectors": {
        "product_container": "li.product",
        "product_name": "h3.product-title a",
        "price": "span.price",
        "in_stock": ".instock",
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

def test_scrape_page_tcgkauppa_stock_detection():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    in_stock = [p for p in products if p["in_stock"] is True]
    out_stock = [p for p in products if p["in_stock"] is False]
    assert len(in_stock) == 6
    assert len(out_stock) == 42

def test_scrape_page_tcgkauppa_currency():
    html = Path("tests/fixtures/tcgkauppa.fi/page1.html").read_text()
    products = scrape_page(html, TCGKAUPPA_CFG)
    assert all(p["currency"] == "EUR" for p in products)


# ── scrape_page: peliparatiisi.net (Shopify Dawn inverted badge) ─────────────

PELIPARATIISI_CFG = {
    "site_name": "Peliparatiisi",
    "currency": "EUR",
    "stock_mode": "badge_text",
    "stock_badge_text": "Sold out",
    "selectors": {
        "product_container": "li.grid__item",
        "product_name": "h3.card__heading.h5 a",
        "price": ".price-item--sale",
        "price_fallback": ".price-item--regular",
        "in_stock": ".badge",
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

def test_scrape_page_peliparatiisi_stock_detection():
    html = Path("tests/fixtures/peliparatiisi.net/page1.html").read_text()
    products = scrape_page(html, PELIPARATIISI_CFG)
    sold_out = [p for p in products if p["in_stock"] is False]
    in_stock = [p for p in products if p["in_stock"] is True]
    assert len(sold_out) == 12
    assert len(in_stock) == 4

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
    "stock_mode": "attribute",
    "selectors": {
        "product_container": '[data-testid="product-card-container"]',
        "product_name": '[data-testid="product-card-name-link"] p',
        "price": ".lipscore-rating-small",
        "in_stock": ".lipscore-rating-small",
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
    assert all(p["in_stock"] is False for p in products)


# ── scrape_page: poromagia.com (product_line only, no product_pod) ───────────

POROMAGIA_CFG = {
    "site_name": "Poromagia",
    "currency": "EUR",
    "stock_mode": "normal",
    "selectors": {
        "product_container": "article.product_line",
        "product_name": "h3 a",
        "price": ".price_color",
        "in_stock": ".instock.availability",
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
    "stock_mode": "badge_text",
    "stock_badge_text": "Ei saatavilla",
    "container_scope": "ul[data-test-id='brand-product-list']",
    "selectors": {
        "product_container": "li",
        "product_name": "a[data-test-id='product-card-link']",
        "price": "[data-test-id='product-card-price']",
        "in_stock": "p",
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
    out_of_stock = [p for p in products if p["in_stock"] is False]
    assert len(out_of_stock) == 4


# ── scrape_page: spelparken.se (Shopify Dawn, SEK, badge_text stock) ─────────

SPELPARKEN_CFG = {
    "site_name": "Spelparken",
    "currency": "SEK",
    "stock_mode": "badge_text",
    "stock_badge_text": "Slutsåld",
    "selectors": {
        "product_container": "li.grid__item",
        "product_name": "h3.card__heading a",
        "price": ".price-item--sale",
        "price_fallback": ".price-item--regular",
        "in_stock": ".card__badge .badge",
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
    sold_out = [p for p in products if p["in_stock"] is False]
    assert len(sold_out) == 1
    assert "Obsidian" in sold_out[0]["raw_name"]


def test_scrape_page_spelparken_nyhet_badge_is_in_stock():
    """Product with 'Nyhet' badge must NOT be treated as out of stock."""
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    nyhet = next(p for p in products if "Twilight" in p["raw_name"])
    assert nyhet["in_stock"] is True


def test_scrape_page_spelparken_currency_is_sek():
    html = Path("tests/fixtures/spelparken.se/page1.html").read_text()
    products = scrape_page(html, SPELPARKEN_CFG)
    assert all(p["currency"] == "SEK" for p in products)


# ── product_url extraction: anchor-as-container (karukortti.fi) ────────────────

# Mirrors site_configs/karukortti.fi.json — product_url is null because the
# container itself is the <a>.
KARUKORTTI_CFG = {
    "site_name": "KaruKortti",
    "selectors": {
        "product_container": 'a[data-selector="list-product-view"]',
        "product_name": '[data-selector="os-theme-product-list-name"]',
        "price": '[data-selector="os-theme-product-list-price-regular"]',
        "in_stock": ".product-sold-out-label",
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
