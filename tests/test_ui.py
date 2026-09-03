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


# ── link ──────────────────────────────────────────────────────────────────────

def test_link_puts_the_name_inside_an_anchor_to_the_shop():
    out = ui.link("https://shop.fi/p/1", "Ascended Heroes ETB")
    assert 'href="https://shop.fi/p/1"' in out
    assert ">Ascended Heroes ETB</a>" in out
    assert 'target="_blank"' in out


def test_link_without_a_url_is_the_bare_name():
    """A link that goes nowhere is worse than text: no anchor at all."""
    assert ui.link(None, "Ascended Heroes ETB") == "Ascended Heroes ETB"
    assert ui.link("", "Ascended Heroes ETB") == "Ascended Heroes ETB"


def test_link_refuses_a_scheme_it_should_not_follow():
    assert ui.link("javascript:alert(1)", "Box") == "Box"
    assert ui.link("/kauppa/box", "Box") == "Box"


def test_link_escapes_the_name_and_the_url():
    out = ui.link('https://shop.fi/?q="x"', "Box <b>1</b> & 2")
    assert "<b>" not in out
    assert "&lt;b&gt;" in out and "&amp;" in out
    assert '&quot;x&quot;' in out


# ── html_table ────────────────────────────────────────────────────────────────

def test_html_table_writes_a_header_and_a_row_per_record():
    out = ui.html_table(["A", "B"], [["1", "2"], ["3", "4"]])
    assert "<th>A</th><th>B</th>" in out
    assert "<tr><td>1</td><td>2</td></tr>" in out
    assert out.count("<tr") == 3  # header plus two rows


def test_html_table_marks_only_the_highlighted_rows():
    out = ui.html_table(["A"], [["1"], ["2"]], highlight=[False, True])
    assert '<tr><td>1</td></tr>' in out
    assert '<tr class="hit"><td>2</td></tr>' in out


def test_html_table_tolerates_a_short_highlight_list():
    """A mismatch should leave rows unmarked, not raise on a page render."""
    out = ui.html_table(["A"], [["1"], ["2"]], highlight=[True])
    assert out.count('class="hit"') == 1


def test_html_table_keeps_named_columns_on_one_line():
    out = ui.html_table(["A", "B"], [["1", "2"]], nowrap=(1,))
    assert '<td>1</td><td class="nowrap">2</td>' in out


def test_html_table_carries_cell_html_through_unchanged():
    """Cells are HTML by contract, which is what makes the name a link."""
    out = ui.html_table(["A"], [['<a href="https://x.fi">n</a>']])
    assert '<a href="https://x.fi">n</a>' in out


def test_html_table_of_no_rows_still_renders():
    out = ui.html_table(["A"], [])
    assert "<tbody></tbody>" in out
