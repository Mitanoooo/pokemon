"""Guards on config fields that used to be hardcoded in Python."""
import json
from pathlib import Path

import pytest

CONFIG_DIR = Path(__file__).parent.parent / "site_configs"

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


def test_offset_pagination_configs_declare_page_size():
    for path in sorted(CONFIG_DIR.glob("*.json")):
        pagination = json.loads(path.read_text(encoding="utf-8")).get("pagination") or {}
        if pagination.get("type") == "offset":
            assert isinstance(pagination.get("page_size"), int), path
