"""Guards on config fields that used to be hardcoded in Python."""
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scraper.paginator import source_urls
from scraper.parser import AVAILABILITY_FORMS, AVAILABILITY_STATES, availability_forms
from scraper.price_parser import DEFAULT_MAX_PRICE

CONFIG_DIR = Path(__file__).parent.parent / "site_configs"

# Replaced by the availability block in ticket 15. A config naming any of these
# is one the parser now ignores, which reads as a site that tracks nothing.
RETIRED_STOCK_KEYS = ("stock_mode", "stock_badge_text")

# Sites that formerly lived in price_parser._DOT_DECIMAL_SITES — the behaviour
# now has to be spelled out in each config.
DOT_DECIMAL_CONFIGS = [
    "maxgaming.fi.json",
    "spelexperten.fi.json",
    "pelimies.fi.json",
    "lelupartanen.fi.json",
    "karkkainen.com.json",
    "pelikrypta.fi.json",
    "fantasialinna.com.json",
]


def _load(filename: str) -> dict:
    return json.loads((CONFIG_DIR / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename", DOT_DECIMAL_CONFIGS)
def test_dot_decimal_sites_declare_separator(filename):
    assert _load(filename)["decimal_separator"] == "dot"


def test_declared_decimal_separators_are_recognised():
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config.get("decimal_separator", "comma") in ("dot", "comma"), path


def test_declared_max_prices_are_above_the_default_ceiling():
    """max_price only exists to raise the guard — a lower value is a mistake."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        max_price = json.loads(path.read_text(encoding="utf-8")).get("max_price")
        if max_price is not None:
            assert isinstance(max_price, (int, float)), path
            assert max_price > DEFAULT_MAX_PRICE, path


def test_disabled_configs_explain_themselves():
    """A site taken out of the run has to say why (issue 04)."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("disabled"):
            assert config.get("notes"), path


def test_offset_pagination_configs_declare_page_size():
    for path in sorted(CONFIG_DIR.glob("*.json")):
        pagination = json.loads(path.read_text(encoding="utf-8")).get("pagination") or {}
        if pagination.get("type") == "offset":
            assert isinstance(pagination.get("page_size"), int), path


# ── availability block ────────────────────────────────────────────────────────

def test_no_config_still_names_a_retired_stock_key():
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        for key in RETIRED_STOCK_KEYS:
            assert key not in config, f"{path.name} still has {key}"
        assert "in_stock" not in (config.get("selectors") or {}), path.name


def test_availability_states_are_all_in_the_allowed_set():
    for path in sorted(CONFIG_DIR.glob("*.json")):
        block = json.loads(path.read_text(encoding="utf-8")).get("availability")
        if not block:
            continue
        states = list((block.get("text_map") or {}).values())
        states += list((block.get("container_class_map") or {}).values())
        states += list(((block.get("attribute") or {}).get("map") or {}).values())
        presence = block.get("presence") or {}
        states += [presence[k] for k in ("present", "absent") if presence.get(k)]
        if block.get("absent_means"):
            states.append(block["absent_means"])
        if block.get("default"):
            states.append(block["default"])
        for state in states:
            assert state in AVAILABILITY_STATES, f"{path.name}: {state}"


def test_availability_blocks_configure_at_least_one_form():
    """A block that only sets a default would report as tracked but detect nothing."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("availability"):
            assert availability_forms(config), path.name


def test_availability_blocks_have_no_unknown_keys():
    allowed = set(AVAILABILITY_FORMS) | {"selector", "default", "absent_means"}
    for path in sorted(CONFIG_DIR.glob("*.json")):
        block = json.loads(path.read_text(encoding="utf-8")).get("availability") or {}
        assert set(block) <= allowed, f"{path.name}: {set(block) - allowed}"


# ── preorder URLs ─────────────────────────────────────────────────────────────

def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def test_preorder_urls_is_a_list_of_absolute_urls_on_the_sites_own_host():
    """A relative or foreign URL here would silently scrape the wrong shop."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        preorder_urls = config.get("preorder_urls")
        if preorder_urls is None:
            continue
        assert isinstance(preorder_urls, list) and preorder_urls, path.name
        site_hosts = {_host(u) for u in source_urls(config)}
        for url in preorder_urls:
            assert urlparse(url).scheme in ("http", "https"), f"{path.name}: {url}"
            assert _host(url) in site_hosts, f"{path.name}: {url}"


def test_preorder_urls_do_not_repeat_a_normal_source_url():
    """A URL scraped twice per run would only tag its listings preorder by luck."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        preorder_urls = config.get("preorder_urls") or []
        assert len(set(preorder_urls)) == len(preorder_urls), path.name
        assert not set(preorder_urls) & set(source_urls(config)), path.name


def test_text_map_and_attribute_forms_have_something_to_read():
    """text_map without a selector reads the whole container; attribute needs a name."""
    for path in sorted(CONFIG_DIR.glob("*.json")):
        block = json.loads(path.read_text(encoding="utf-8")).get("availability") or {}
        if block.get("presence"):
            assert (block["presence"].get("selector") or block.get("selector")), path.name
        if block.get("attribute"):
            assert block["attribute"].get("name"), path.name
            assert block["attribute"].get("map"), path.name
