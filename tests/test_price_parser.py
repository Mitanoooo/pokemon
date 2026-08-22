"""Tests for parse_price — one test per format variant from site_notes.md."""
import logging
import pytest
from scraper.price_parser import parse_price


# ── comma decimal (default) ──────────────────────────────────────────────────

def test_comma_decimal_with_euro_suffix():
    assert parse_price("34,90 €", {}) == 34.90

def test_comma_decimal_no_space_before_euro():
    # muksumassi.fi: "14,95€"
    assert parse_price("14,95€", {}) == 14.95

def test_comma_decimal_with_xa0_before_euro():
    # poromagia.com: "21,95\xa0€"
    assert parse_price("21,95\xa0€", {}) == 21.95


# ── dot decimal ───────────────────────────────────────────────────────────────

DOT = {"decimal_separator": "dot"}


def test_dot_decimal_with_euro_suffix():
    # maxgaming.fi: "219.90 €"
    assert parse_price("219.90 €", {"site_name": "MaxGaming", **DOT}) == 219.90

def test_dot_decimal_euro_prefix():
    # spelexperten.fi: "€7.55"
    assert parse_price("€7.55", {"site_name": "Spelexperten", **DOT}) == 7.55

def test_dot_decimal_pelimies():
    # pelimies.fi: "49.90 €"
    assert parse_price("49.90 €", {"site_name": "Pelimies", **DOT}) == 49.90

def test_decimal_separator_comma_is_explicit_default():
    assert parse_price("39,90 €", {"decimal_separator": "comma"}) == 39.90

def test_site_name_alone_no_longer_implies_dot_decimal():
    # The hardcoded dot-decimal site set is gone — only the config field decides.
    assert parse_price("219,90 €", {"site_name": "MaxGaming"}) == 219.90


# ── € prefix stripping ────────────────────────────────────────────────────────

def test_euro_prefix_comma_decimal():
    # pbcards.fi: "€5,95"
    assert parse_price("€5,95", {}) == 5.95

def test_euro_prefix_godofcards():
    # godofcards.com after "Sale price" stripping: "€82,63"
    assert parse_price("€82,63", {}) == 82.63

def test_euro_prefix_pelikrypta_dot():
    # pelikrypta.fi: "€7.00"
    assert parse_price("€7.00", {"site_name": "Pelikrypta (Ikamaa)", "decimal_separator": "dot"}) == 7.00


# ── EUR suffix stripping ──────────────────────────────────────────────────────

def test_eur_suffix_stripped():
    # blockhousegames.net after visually-hidden removal: "59,90 EUR"
    assert parse_price("59,90 EUR", {}) == 59.90

def test_eur_suffix_with_euro_prefix():
    # peliparatiisi.net: "€5,90 EUR"
    assert parse_price("€5,90 EUR", {}) == 5.90


# ── SEK / kr suffix ───────────────────────────────────────────────────────────

def test_kr_suffix_with_thousands_space():
    # spelparken.se: "5 499 kr"
    assert parse_price("5 499 kr", {}) == 5499.0

def test_kr_suffix_simple():
    assert parse_price("17 kr", {}) == 17.0


# ── non-breaking space normalisation ─────────────────────────────────────────

def test_xa0_as_decimal_separator_stripped():
    # kerailykortti.fi xa0 in price: "34,90\xa0€"
    assert parse_price("34,90\xa0€", {}) == 34.90


# ── multiple prices — last wins ───────────────────────────────────────────────

def test_multiple_prices_last_wins_space_separated():
    # tcgkauppa.fi sale: "4,90\xa0€ 3,90\xa0€"
    assert parse_price("4,90\xa0€ 3,90\xa0€", {}) == 3.90

def test_multiple_prices_last_wins_xa0_separated():
    # pbcards.fi: "€5,95\xa0€4,95"
    assert parse_price("€5,95\xa0€4,95", {}) == 4.95


# ── "Sale price" prefix (godofcards.com) ─────────────────────────────────────

def test_sale_price_text_prefix_stripped():
    assert parse_price("Sale price82,63€", {}) == 82.63

def test_sale_price_with_space():
    assert parse_price("Sale price 82,63€", {}) == 82.63


# ── bare float (lelupartanen.fi itemprop) ────────────────────────────────────

def test_bare_float_dot_decimal():
    assert parse_price("16.95", {"site_name": "Lelukauppa Partanen", "decimal_separator": "dot"}) == 16.95


# ── suspicious prices ─────────────────────────────────────────────────────────

def test_price_below_2_returns_none(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_price("1,00 €", {})
    assert result is None
    assert "suspicious" in caplog.text.lower() or "warning" in caplog.text.lower() or caplog.records

def test_price_above_2000_returns_none(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_price("1 394 072,10 €", {})
    assert result is None

def test_price_exactly_2_is_valid():
    assert parse_price("2,00 €", {}) == 2.00

def test_price_exactly_2000_is_valid():
    assert parse_price("2000,00 €", {}) == 2000.00


# ── per-config max_price override ─────────────────────────────────────────────
# Some shops list factory cases (porvoonpelikauppa.fi "tehdaslaatikko") well
# above the default 2000 € ceiling, so the ceiling is raisable per site.

def test_max_price_override_admits_a_factory_case_price():
    assert parse_price("2 850,00 € ", {"max_price": 5000.0}) == 2850.00

def test_max_price_override_still_rejects_above_its_own_ceiling():
    assert parse_price("6 000,00 €", {"max_price": 5000.0}) is None

def test_max_price_override_does_not_relax_the_lower_bound():
    assert parse_price("1,00 €", {"max_price": 5000.0}) is None

def test_max_price_override_boundary_is_inclusive():
    assert parse_price("5000,00 €", {"max_price": 5000.0}) == 5000.00

def test_default_ceiling_unchanged_without_override():
    assert parse_price("2 850,00 €", {}) is None


# ── Peliparatiisi: comma decimal, not dot decimal ────────────────────────────

def test_peliparatiisi_comma_decimal_not_multiplied():
    # Peliparatiisi uses Finnish comma-decimal; must yield 39.9 not 3990.0
    assert parse_price("€39,90 EUR", {"site_name": "Peliparatiisi"}) == 39.90
