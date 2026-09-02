import logging
from typing import Optional

from bs4 import BeautifulSoup, Tag

from scraper.price_parser import parse_price, within_price_bounds

logger = logging.getLogger(__name__)


def _sel(config: dict, key: str) -> Optional[str]:
    return (config.get("selectors") or {}).get(key)


AVAILABILITY_STATES = ("in_stock", "out_of_stock", "preorder", "unknown")

# Resolution order of the availability block's forms. First hit wins — but a
# page fetched from a preorder URL beats all of them (see detect_availability).
AVAILABILITY_FORMS = ("text_map", "presence", "container_class_map", "attribute")

# Not a form: `absent_means` reads nothing off the page. It says what a listing
# vanishing from a stock-filtered listing URL means, and the runner applies it
# after a run rather than detect_availability doing it per container. It still
# belongs in availability_mode, so By site says where a shop's out-of-stock
# readings come from.
AVAILABILITY_ABSENT_MODE = "absent"

# availability_text is stored so a misread badge can be re-diagnosed without
# re-scraping. 120 chars is enough for "Ennakkotilaus 12.9.2026" and its
# neighbours without turning listings into a text dump.
AVAILABILITY_TEXT_CAP = 120


def _norm(text: str) -> str:
    """Casefold and collapse whitespace, so badge text compares predictably."""
    return " ".join(text.split()).casefold()


def _text_of(el: Tag) -> Optional[str]:
    return el.get_text(strip=True)[:AVAILABILITY_TEXT_CAP] or None


def _state(value: str, config: dict) -> str:
    """Clamp a config-supplied state to AVAILABILITY_STATES.

    A typo such as `"instock"` would otherwise travel down to the availability
    CHECK constraint and raise on the first insert, which run_site turns into a
    site-wide failure. One unknown listing plus a warning is cheaper to read.
    """
    if value in AVAILABILITY_STATES:
        return value
    logger.warning(
        "Availability state %r is not one of %s (site: %s) — reading as unknown",
        value, AVAILABILITY_STATES, config.get("site_name", ""),
    )
    return "unknown"


def availability_forms(config: dict) -> Optional[str]:
    """The config's availability forms, comma-joined in precedence order.

    Written to sites.availability_mode. None means the site tracks nothing,
    which the app reports as "not tracked" rather than as all-unknown. A block
    holding only a `default` tracks nothing either, so it reads as None too.

    `absent_means` is appended as "absent" after the page-reading forms. It is
    not one of them, but a site that only knows an item is gone because it fell
    off the page does track availability, and the mode column is where that
    shows.
    """
    block = config.get("availability") or {}
    modes = [f for f in AVAILABILITY_FORMS if block.get(f)]
    if block.get("absent_means"):
        modes.append(AVAILABILITY_ABSENT_MODE)
    return ",".join(modes) or None


def detect_availability(
    container_el: Tag, config: dict, from_preorder_url: bool = False
) -> "tuple[str, Optional[str]]":
    """Return (availability, availability_text) for one product container.

    availability is one of AVAILABILITY_STATES. availability_text is the raw
    text that produced it, capped, or None when the state came from a default.

    A page fetched from one of the site's preorder URLs outranks every form: the
    shop put the item in that category deliberately, while its badges describe
    orderability, and a preorder is orderable. Ranked after the forms (as ticket
    15 left it) the flag was dead for the 14 `presence` sites, whose blocks set
    both `present` and `absent` and so always produce a state.

    Below that, forms resolve in AVAILABILITY_FORMS order and the first one that
    produces a state wins; a form that matches nothing falls through to the next.
    No availability block at all means unknown, whatever the page says — an
    untracked site stays untracked rather than reading preorder-for-everything,
    though listings.from_preorder_url still records where the sighting came from.
    """
    block = config.get("availability")
    if not block:
        return "unknown", None

    if from_preorder_url:
        return "preorder", "(preorder url)"

    selector = block.get("selector")

    text_map = block.get("text_map")
    if text_map:
        elements = container_el.select(selector) if selector else [container_el]
        haystacks = [(el, _norm(el.get_text())) for el in elements]
        # Longest key first across every element, not per element: a container
        # printing both "Varastossa" and "Ennakkotilaus 12.9.2026" must resolve
        # to preorder whichever badge the shop renders first.
        for key in sorted(text_map, key=len, reverse=True):
            needle = _norm(key)
            for el, haystack in haystacks:
                if needle in haystack:
                    return _state(text_map[key], config), _text_of(el)

    presence = block.get("presence")
    if presence:
        sel = presence.get("selector") or selector
        el = container_el.select_one(sel) if sel else None
        if el is not None:
            if presence.get("present"):
                return _state(presence["present"], config), _text_of(el)
        elif presence.get("absent"):
            return _state(presence["absent"], config), None

    class_map = block.get("container_class_map")
    if class_map:
        classes = container_el.get("class") or []
        for cls, state in class_map.items():
            if cls in classes:
                joined = " ".join(classes)
                # The whole list is the more useful diagnostic, but only when it
                # fits: swagykarp.fi cards carry ~20 classes and the cap would
                # cut off the very class that decided the state.
                text = joined if len(joined) <= AVAILABILITY_TEXT_CAP else cls
                return _state(state, config), text[:AVAILABILITY_TEXT_CAP]

    attribute = block.get("attribute")
    if attribute:
        el = container_el.select_one(selector) if selector else container_el
        value = el.get(attribute.get("name", ""), "") if el is not None else ""
        if isinstance(value, list):
            # bs4 hands back a list for multi-valued attributes such as class.
            value = " ".join(value)
        for key, state in (attribute.get("map") or {}).items():
            if _norm(key) == _norm(value):
                return _state(state, config), value[:AVAILABILITY_TEXT_CAP]

    return _state(block.get("default", "unknown"), config), None


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
            if not within_price_bounds(value, config):
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
            value = float(itemprop_price)
        except ValueError:
            pass
        else:
            # Same bounds as every other price path — an attribute placeholder
            # is no more trustworthy than one printed in the page text.
            if not within_price_bounds(value, config):
                logger.warning("Suspicious attribute price %.2f (site: %s)", value, site_name)
                return None
            return value

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


def find_containers(soup: BeautifulSoup, config: dict) -> "list[Tag]":
    """Every product container on a parsed page, honouring container_scope.

    container_scope pre-filters the DOM (prisma.fi's carousel would otherwise
    count as listings). A scope selector that matches nothing means no
    containers, not a page-wide fallback.
    """
    container_sel = _sel(config, "product_container")
    if not container_sel:
        return []

    scope_sel = config.get("container_scope")
    if not scope_sel:
        return soup.select(container_sel)

    scope_el = soup.select_one(scope_sel)
    if scope_el is None:
        return []
    return scope_el.select(container_sel)


def scrape_page(
    html: str, config: dict, from_preorder_url: bool = False
) -> list[dict]:
    """Parse one page of HTML and return a list of product dicts.

    Each dict has: raw_name, price (float or None), currency, availability,
    availability_text, product_url.

    from_preorder_url says the page came from one of the site's preorder_urls,
    which makes every product on it read `preorder` whatever its badge says —
    see detect_availability for why that outranks the forms.

    Supports container_scope config key to pre-filter the DOM (e.g. prisma.fi
    carousel exclusion).
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = find_containers(soup, config)

    if not containers:
        return []

    currency = config.get("currency", "EUR")
    results = []

    for c in containers:
        raw_name = _extract_name(c, config)
        price = _extract_price(c, config)
        availability, availability_text = detect_availability(
            c, config, from_preorder_url=from_preorder_url
        )
        product_url = _extract_url(c, config)

        results.append({
            "raw_name": raw_name,
            "price": price,
            "currency": currency,
            "availability": availability,
            "availability_text": availability_text,
            "product_url": product_url,
        })

    return results
