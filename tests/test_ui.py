"""Helpers the pages share. Streamlit itself is not exercised here, only the
pure functions the tables are built from."""
from app import ui


# ── when ──────────────────────────────────────────────────────────────────────

def test_when_converts_a_stored_utc_stamp_to_helsinki_summer_time():
    """EEST is UTC+3, so an event written at 15:01 UTC happened at 18:01 here."""
    assert ui.when("2026-09-03 15:01:08") == "2026-09-03 18:01"


def test_when_converts_winter_time_at_the_other_offset():
    """EET is UTC+2. A fixed offset would put this hour wrong for half the year."""
    assert ui.when("2026-01-15 15:01:08") == "2026-01-15 17:01"


def test_when_crosses_the_date_boundary():
    assert ui.when("2026-09-03 22:30:00") == "2026-09-04 01:30"


def test_when_of_nothing_is_empty():
    assert ui.when(None) == ""
    assert ui.when("") == ""


def test_when_passes_through_a_stamp_it_cannot_parse():
    """A cell that shows something odd beats a cell that shows nothing."""
    assert ui.when("not a timestamp at all") == "not a timestamp "


# ── parse_keywords ────────────────────────────────────────────────────────────

def test_parse_keywords_splits_on_commas_so_a_keyword_can_be_a_phrase():
    assert ui.parse_keywords("ascended, chaos rising") == ["ascended", "chaos rising"]


def test_parse_keywords_drops_empty_entries():
    assert ui.parse_keywords(" ascended , , ") == ["ascended"]


def test_parse_keywords_of_nothing_is_empty():
    assert ui.parse_keywords(None) == []
    assert ui.parse_keywords("") == []


# ── matches_keywords ──────────────────────────────────────────────────────────

def test_matches_keywords_ignores_case():
    assert ui.matches_keywords("Pokémon TCG ME02.5 Ascended Heroes ETB", ["ascended"])


def test_matches_keywords_needs_only_one_hit():
    name = "Pokémon ME04 Chaos Rising Elite Trainer Box"
    assert ui.matches_keywords(name, ["ascended", "chaos rising"])


def test_matches_keywords_is_false_without_a_hit():
    assert not ui.matches_keywords("Prismatic Evolutions ETB", ["ascended"])


def test_matches_keywords_with_no_keywords_is_false():
    """No keywords means no highlight, not everything highlighted."""
    assert not ui.matches_keywords("Prismatic Evolutions ETB", [])


def test_matches_keywords_of_a_missing_name_is_false():
    assert not ui.matches_keywords(None, ["ascended"])
