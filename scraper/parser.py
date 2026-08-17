import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from scraper.price_parser import parse_price

logger = logging.getLogger(__name__)


def _sel(config: dict, key: str) -> Optional[str]:
    return (config.get("selectors") or {}).get(key)


def detect_stock(container_el: Tag, config: dict) -> Optional[bool]:
    """Return True (in stock), False (out of stock), or None (unknown).

    Mode is driven by config['stock_mode']:
      - 'normal'          : presence of in_stock selector = in stock
      - 'inverted'        : absence of in_stock selector = in stock
      - 'badge_text'      : badge with exact text (stock_badge_text) = out of stock
      - 'container_class' : container's own class list checked for instock/outofstock/unavailable
      - 'attribute'       : data-ls-availability on the in_stock element
      - None / 'unknown'  : return None
    """
    mode = config.get("stock_mode")
    if not mode or mode == "unknown":
        return None

    sel = _sel(config,"in_stock")

    if mode == "normal":
        if not sel:
            return None
        return container_el.select_one(sel) is not None

    if mode == "inverted":
        if not sel:
            return None
        return container_el.select_one(sel) is None

    if mode == "badge_text":
        badge_text = config.get("stock_badge_text", "")
        if not sel:
            return None
        # Search all matching elements (e.g. prisma.fi uses <p> which may appear
        # multiple times; we need the one with the exact out-of-stock text)
        for badge in container_el.select(sel):
            if badge.get_text(strip=True) == badge_text:
                return False
        return True

    if mode == "container_class":
        classes = container_el.get("class") or []
        if "instock" in classes:
            return True
        if "outofstock" in classes or "unavailable" in classes:
            return False
        return None

    if mode == "attribute":
        if not sel:
            return None
        el = container_el.select_one(sel)
        if el is None:
            return None
        avail = el.get("data-ls-availability", "")
        if avail == "InStock":
            return True
        if avail == "OutOfStock":
            return False
        return None

    return None


def _extract_price(container_el: Tag, config: dict) -> Optional[float]:
    """Extract the price from a container element using the config selectors.

    Handles special cases:
    - karkkainen.com: data-ls-price attribute on .lipscore-rating-small
    - WooCommerce <ins>/<del> sale prices
    - .visually-hidden span stripping (blockhousegames.net, pelienmaa.com)
    - price_fallback selector when primary returns empty
    - maxgaming.fi product name multi-line (handled in name extraction)
    """
    sel = _sel(config,"price")
    site_name = config.get("site_name", "")
    if not sel:
        return None

    el = container_el.select_one(sel)
    if el is None:
        return None

    # karkkainen.com: price in data-ls-price attribute (dot decimal float)
    ls_price = el.get("data-ls-price")
    if ls_price is not None:
        try:
            value = float(ls_price)
            if value < 2.0 or value > 2000.0:
                logger.warning("Suspicious attribute price %.2f (site: %s)", value, site_name)
                return None
            return value
        except ValueError:
            return None

    # lelupartanen.fi: bare float in itemprop="Price" content attribute
    itemprop_price = el.get("content") if el.get("itemprop") == "Price" else None
    if itemprop_price is None:
        # also check price element itself
        itemprop_el = container_el.select_one('[itemprop="Price"]')
        if itemprop_el:
            itemprop_price = itemprop_el.get("content")
    if itemprop_price is not None:
        try:
            return float(itemprop_price)
        except ValueError:
            pass

    # WooCommerce <ins>/<del>: extract <ins> text only
    ins_el = el.select_one("ins")
    if ins_el:
        el = ins_el

    # Strip .visually-hidden spans before reading text
    for vh in el.select(".visually-hidden"):
        vh.decompose()

    # Try primary selector text
    raw = el.get_text()
    price = parse_price(raw, config)

    # Fallback selector (e.g. .price-item--regular when .price-item--sale is absent)
    if price is None:
        fallback_sel = _sel(config,"price_fallback")
        if fallback_sel:
            fb_el = container_el.select_one(fallback_sel)
            if fb_el:
                price = parse_price(fb_el.get_text(), config)

    return price


def _extract_name(container_el: Tag, config: dict) -> str:
    """Extract the product name from a container element."""
    sel = _sel(config,"product_name")
    if not sel:
        return ""
    el = container_el.select_one(sel)
    if el is None:
        return ""

    text = el.get_text(strip=True)

    # maxgaming.fi: name element has "Pokémon\n<actual title>" — take last non-empty line
    if config.get("site_name") == "MaxGaming":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = lines[-1] if lines else text

    return text


def _extract_url(container_el: Tag, config: dict) -> str:
    sel = _sel(config,"product_url")
    if not sel:
        # Some shops (karukortti.fi) use the <a> itself as the product
        # container, so there is no inner anchor to select — use its own href.
        if container_el.name == "a":
            return container_el.get("href", "") or ""
        return ""
    el = container_el.select_one(sel)
    if el is None:
        return ""
    return el.get("href", "") or el.get("data-ls-product-url", "")


def scrape_page(html: str, config: dict) -> list[dict]:
    """Parse one page of HTML and return a list of product dicts.

    Each dict has: raw_name, price (float or None), currency, in_stock
    (bool or None), product_url.

    Supports container_scope config key to pre-filter the DOM (e.g. prisma.fi
    carousel exclusion).
    """
    soup = BeautifulSoup(html, "html.parser")
    container_sel = _sel(config,"product_container")
    if not container_sel:
        return []

    scope_sel = config.get("container_scope")
    if scope_sel:
        scope_el = soup.select_one(scope_sel)
        if scope_el is None:
            return []
        containers = scope_el.select(container_sel)
    else:
        containers = soup.select(container_sel)

    if not containers:
        return []

    currency = config.get("currency", "EUR")
    results = []

    for c in containers:
        raw_name = _extract_name(c, config)
        price = _extract_price(c, config)
        in_stock = detect_stock(c, config)
        product_url = _extract_url(c, config)

        results.append({
            "raw_name": raw_name,
            "price": price,
            "currency": currency,
            "in_stock": in_stock,
            "product_url": product_url,
        })

    return results
