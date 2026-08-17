"""Tests for scraper.paginator.paginate."""
import pytest
from scraper.paginator import is_paginated, paginate


# ── none ─────────────────────────────────────────────────────────────────────

def test_paginate_none_returns_single_source_url():
    cfg = {
        "source_url": "https://example.com/shop/",
        "pagination": {"type": "none"},
    }
    assert paginate(cfg) == ["https://example.com/shop/"]


# ── url_pattern (absolute) ────────────────────────────────────────────────────

ABS_CFG = {
    "source_url": "https://example.com/shop/",
    "pagination": {
        "type": "url_pattern",
        "url_pattern": "https://example.com/shop/page/{page}/",
        "max_pages": 3,
    },
}


def test_paginate_url_pattern_page1_is_source_url():
    urls = paginate(ABS_CFG)
    assert urls[0] == "https://example.com/shop/"


def test_paginate_url_pattern_no_substitution_on_page1():
    urls = paginate(ABS_CFG)
    assert "{page}" not in urls[0]
    assert "page/1" not in urls[0]


def test_paginate_url_pattern_absolute_full_list():
    assert paginate(ABS_CFG) == [
        "https://example.com/shop/",
        "https://example.com/shop/page/2/",
        "https://example.com/shop/page/3/",
    ]


# ── url_pattern (relative) ────────────────────────────────────────────────────

REL_CFG = {
    "source_url": "https://kevinshobbyshop.com/shop/?yith_wcan=1&filter_game=pokemon&query_type_game=or",
    "pagination": {
        "type": "url_pattern",
        "url_pattern": "/shop/page/{page}/?yith_wcan=1&filter_game=pokemon&query_type_game=or",
        "max_pages": 3,
    },
}


def test_paginate_url_pattern_relative_prepends_base_domain():
    urls = paginate(REL_CFG)
    assert urls[1] == "https://kevinshobbyshop.com/shop/page/2/?yith_wcan=1&filter_game=pokemon&query_type_game=or"


def test_paginate_url_pattern_relative_page1_is_source_url():
    urls = paginate(REL_CFG)
    assert urls[0] == REL_CFG["source_url"]


# ── url_pattern (query-string only) ───────────────────────────────────────────

QUERY_CFG = {
    "source_url": "https://blockhousegames.net/collections/pokemon-tcg",
    "pagination": {
        "type": "url_pattern",
        "url_pattern": "?page={page}",
        "max_pages": 2,
    },
}


def test_paginate_url_pattern_query_only_resolved_against_source_url():
    urls = paginate(QUERY_CFG)
    assert urls == [
        "https://blockhousegames.net/collections/pokemon-tcg",
        "https://blockhousegames.net/collections/pokemon-tcg?page=2",
    ]


# ── offset ────────────────────────────────────────────────────────────────────

OFFSET_CFG = {
    "source_url": "https://www.karkkainen.com/verkkokauppa/kerailykortit",
    "pagination": {
        "type": "offset",
        "url_pattern": "?offset={offset}",
        "max_pages": 3,
    },
}


def test_paginate_offset_page1_is_source_url():
    urls = paginate(OFFSET_CFG)
    assert urls[0] == "https://www.karkkainen.com/verkkokauppa/kerailykortit"


def test_paginate_offset_correct_offsets():
    urls = paginate(OFFSET_CFG)
    assert "offset=60" in urls[1]
    assert "offset=120" in urls[2]


def test_paginate_offset_respects_max_pages():
    urls = paginate(OFFSET_CFG)
    assert len(urls) == 3


def test_paginate_offset_uses_configured_page_size():
    cfg = {
        "source_url": "https://example.com/shop",
        "pagination": {
            "type": "offset",
            "url_pattern": "?offset={offset}",
            "max_pages": 3,
            "page_size": 24,
        },
    }
    assert paginate(cfg) == [
        "https://example.com/shop",
        "https://example.com/shop?offset=24",
        "https://example.com/shop?offset=48",
    ]


# ── swagykarp (url_pattern with known absolute pattern) ───────────────────────

SWAGYKARP_CFG = {
    "source_url": "https://swagykarp.fi/product-category/pokemon-tuotteet/boosterit/",
    "pagination": {
        "type": "url_pattern",
        "url_pattern": "https://swagykarp.fi/product-category/pokemon-tuotteet/boosterit/page/{page}/",
        "max_pages": 5,
    },
}


def test_paginate_swagykarp_returns_5_urls():
    assert len(paginate(SWAGYKARP_CFG)) == 5


def test_paginate_swagykarp_page1_is_source_url():
    urls = paginate(SWAGYKARP_CFG)
    assert urls[0] == "https://swagykarp.fi/product-category/pokemon-tuotteet/boosterit/"


def test_paginate_swagykarp_uses_page_pattern():
    urls = paginate(SWAGYKARP_CFG)
    assert "page/2" in urls[1]
    assert "page/5" in urls[4]
    assert all("swagykarp.fi" in u for u in urls)


# ── is_paginated ──────────────────────────────────────────────────────────────

def test_is_paginated_false_for_type_none():
    assert is_paginated({"pagination": {"type": "none"}}) is False


def test_is_paginated_false_when_pagination_missing_or_null():
    assert is_paginated({}) is False
    assert is_paginated({"pagination": None}) is False


def test_is_paginated_true_for_url_pattern_and_offset():
    assert is_paginated({"pagination": {"type": "url_pattern"}}) is True
    assert is_paginated({"pagination": {"type": "offset"}}) is True
