import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

MIN_PRICE = 2.0
DEFAULT_MAX_PRICE = 2000.0


def within_price_bounds(value: float, config: dict) -> bool:
    """True when value is a plausible sealed-product price for this site.

    The ceiling is raisable per site with "max_price" (porvoonpelikauppa.fi
    lists whole factory cases); the floor is not, because no shop legitimately
    lists sealed product under 2 € — that value is always a placeholder.

    Callers reading a price out of an HTML attribute use this directly;
    parse_price applies it to the value it has parsed out of the page text.
    """
    return MIN_PRICE <= value <= float(config.get("max_price") or DEFAULT_MAX_PRICE)


def parse_price(raw_text: str, config: dict) -> Optional[float]:
    """Parse a raw price string into a float.

    Handles all Finnish/Swedish retailer price format variants documented in
    site_notes.md.  The config's optional "decimal_separator" key ("dot" or
    "comma", default "comma") says which separator the site prints.  Returns
    None and logs a warning for suspicious values — below 2.0, or above the
    config's optional "max_price" (default 2000.0).
    """
    site_name = config.get("site_name", "")
    text = raw_text

    # 1. Normalise non-breaking spaces throughout
    text = text.replace("\xa0", " ")

    # 2. Strip "Sale price" prefix (godofcards.com)
    text = re.sub(r"(?i)^sale\s*price\s*", "", text)

    # 3. Strip EUR suffix
    text = re.sub(r"\bEUR\b", "", text)

    # 4. Strip trailing kr (spelparken.se) — must come before € stripping
    text = re.sub(r"\bkr\b", "", text)

    # 5. Strip € prefix and suffix
    text = text.replace("€", " ")

    # 6. Strip any remaining non-numeric junk from the string while keeping
    #    digits, commas, dots, spaces, and minus
    text = text.strip()

    # 7. Find all numeric tokens (handles "4,90 3,90" → ["4,90", "3,90"])
    tokens = re.findall(r"\d[\d\s]*[.,]?\d*", text)
    if not tokens:
        logger.warning("No numeric value found in price text: %r (site: %s)", raw_text, site_name)
        return None

    # 8. Take the last token (sale price wins over original price)
    last_token = tokens[-1].strip()

    # 9. Remove spaces used as thousands separators
    last_token = last_token.replace(" ", "")

    # 10. Convert decimal separator: comma → dot (unless site uses dot decimal)
    if config.get("decimal_separator", "comma") == "dot":
        # dot is already the decimal separator; remove any commas (thousands)
        last_token = last_token.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", last_token):
        # A comma followed by exactly three digits, with nothing else in the
        # token, is a thousands group rather than a decimal: spelparken.se prints
        # "5,499 kr" for 5499 kr. No shop prices anything to three decimals, and
        # the SEK guard lets a wrong reading through, so 5499 landed as 5.499.
        last_token = last_token.replace(",", "")
    else:
        # comma is the decimal separator; remove any dots (thousands), swap comma → dot
        last_token = last_token.replace(".", "")
        last_token = last_token.replace(",", ".")

    try:
        value = float(last_token)
    except ValueError:
        logger.warning("Could not convert %r to float (site: %s)", last_token, site_name)
        return None

    # 11. Suspicious price guard (EUR only — SEK prices legitimately exceed 2000)
    is_sek = bool(re.search(r"\bkr\b", raw_text))
    if not is_sek and not within_price_bounds(value, config):
        logger.warning(
            "Suspicious price %.2f from %r — returning None (site: %s)",
            value, raw_text, site_name,
        )
        return None

    return value
