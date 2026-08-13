"""Tests for scripts/calibration_candidates.py."""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "calibration_candidates.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("calibration_candidates", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_module()


def _p(pid, name, category="Pokémon Booster", rank=None):
    return {"id": pid, "name": name, "category": category, "rank": rank}


# ── tokenize ──────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_splits_on_punctuation(mod):
    assert mod.tokenize("Pitch-Black: Booster!") == {"pitch", "black", "booster"}


def test_tokenize_drops_noise_tokens(mod):
    # "pokemon", "tcg" and "kpl" appear in most listings, so they carry no signal
    assert mod.tokenize("Pokemon TCG Pitch Black 3 kpl") == {"pitch", "black", "3"}


# ── accent folding ────────────────────────────────────────────────────────────
# tokenize matches [a-z0-9]+, so an accented word would otherwise break into
# fragments ("pokémon" -> "pok", "mon") that no NOISE_TOKENS entry can reach --
# handing every catalog row containing "Pokémon" two free tokens of overlap.

def test_fold_strips_diacritics(mod):
    assert mod.fold("Pokémon") == "pokemon"


def test_tokenize_drops_accented_brand_name_as_noise(mod):
    assert mod.tokenize("Pokémon Pitch Black") == {"pitch", "black"}


def test_tokenize_yields_nothing_for_an_all_noise_accented_name(mod):
    assert mod.tokenize("Pokémon TCG") == set()


def test_tokenize_folds_accents_in_catalog_names_too(mod):
    assert mod.tokenize("Pitch Black Pokémon Center Elite Trainer Box") == {
        "pitch", "black", "center", "elite", "trainer", "box",
    }


# ── pack vs box must stay distinguishable ─────────────────────────────────────
# Pack-vs-box is the most common mapping error, so "box" is not a noise token.

def test_tokenize_keeps_product_form_words(mod):
    assert mod.tokenize("Chaos Rising Booster") != mod.tokenize("Chaos Rising Booster Box")


def test_tokenize_keeps_box(mod):
    assert "box" in mod.tokenize("Chaos Rising Booster Box")


# ── expand_codes ──────────────────────────────────────────────────────────────
# Retailers ship set codes ("Poke ME05 ..."); Cardmarket names the expansion.

def test_expand_codes_adds_expansion_name_behind_set_code(mod):
    assert mod.expand_codes({"me05"}) == {"me05", "pitch", "black"}


def test_expand_codes_leaves_unknown_tokens_alone(mod):
    assert mod.expand_codes({"zz99"}) == {"zz99"}


def test_expand_codes_ignores_two_char_japanese_subset_codes(mod):
    # "m2" collides with accessory model codes -- MaxGaming's "Ultra Pro Charmander
    # M2 Deck Box" is a plastic deck box, and expanding it to "Inferno X" put
    # sealed booster rows at the top of the hint list for a null_mapped listing.
    assert mod.expand_codes({"m2"}) == {"m2"}
    assert mod.expand_codes({"m5"}) == {"m5"}


def test_expand_codes_has_no_unreachable_keys(mod):
    """Every SET_CODES key must survive tokenize, or its entry is dead code."""
    unreachable = [code for code in mod.SET_CODES if mod.tokenize(code) != {code}]
    assert unreachable == []


# ── top_candidates ────────────────────────────────────────────────────────────

def test_top_candidates_orders_by_difflib_ratio(mod):
    products = [
        _p(1, "Pitch Black Booster"),
        _p(2, "Paldean Fates Booster"),
    ]
    assert [c["id"] for c in mod.top_candidates("Pitch Black Booster", products)] == [1, 2]


def test_top_candidates_breaks_ties_on_lower_popularity_rank(mod):
    # Identical names, so the ratio ties and popularity_rank ASC decides.
    products = [_p(1, "Chaos Rising Booster", rank=40), _p(2, "Chaos Rising Booster", rank=4)]
    assert [c["id"] for c in mod.top_candidates("Chaos Rising Booster", products)] == [2, 1]


def test_top_candidates_sorts_missing_rank_last(mod):
    products = [_p(1, "Chaos Rising Booster", rank=None), _p(2, "Chaos Rising Booster", rank=9)]
    assert [c["id"] for c in mod.top_candidates("Chaos Rising Booster", products)] == [2, 1]


def test_top_candidates_respects_top_n(mod):
    products = [_p(i, f"Set {i} Booster") for i in range(10)]
    assert len(mod.top_candidates("Booster", products, top_n=3)) == 3


def test_top_candidates_attaches_rounded_score(mod):
    products = [_p(1, "Pitch Black Booster")]
    (candidate,) = mod.top_candidates("Pitch Black Booster", products)
    assert candidate["score"] == 1.0
    assert candidate["name"] == "Pitch Black Booster"


# ── token_hints ───────────────────────────────────────────────────────────────
# The whole-string difflib ratio in top_candidates is dominated by long retailer
# prefixes, so the correct row can fall outside the top 5. This is the recovery
# path -- "Scarlet &amp; Violet: Paradox Rift booster" scores every Scarlet &
# Violet base-set row above "Paradox Rift Booster" itself.

def test_token_hints_surfaces_row_the_ratio_ranks_below_the_top_five(mod):
    raw = "Scarlet &amp; Violet: Paradox Rift booster"
    products = [
        _p(692088, "Scarlet & Violet Booster"),
        _p(692091, "Scarlet & Violet Sleeved Booster"),
        _p(692092, "Scarlet & Violet Booster Box"),
        _p(692408, "Scarlet & Violet 3-Pack Blister"),
        _p(692095, "Scarlet & Violet 6 Booster Box Case"),
        _p(728716, "Paradox Rift Booster"),
    ]
    top5 = mod.top_candidates(raw, products)
    assert 728716 not in {c["id"] for c in top5}

    hints = mod.token_hints(raw, products, {c["id"] for c in top5})
    assert 728716 in {h["id"] for h in hints}


def test_token_hints_excludes_ids_already_shown(mod):
    products = [_p(1, "Pitch Black Booster"), _p(2, "Pitch Black Booster Box")]
    hints = mod.token_hints("Pitch Black Booster", products, exclude={1})
    assert [h["id"] for h in hints] == [2]


def test_token_hints_skips_rows_sharing_no_distinctive_token(mod):
    products = [_p(1, "Paldean Fates Booster")]
    assert mod.token_hints("Pitch Black Elite Trainer Box", products, exclude=set()) == []


def test_token_hints_returns_empty_when_raw_name_is_all_noise(mod):
    products = [_p(1, "Pitch Black Booster")]
    assert mod.token_hints("Pokemon TCG", products, exclude=set()) == []


def test_token_hints_prefers_higher_token_coverage(mod):
    raw = "Poke ME05 Elite Trainer Box"
    products = [
        _p(1, "Pitch Black Elite Trainer Box", "Pokémon Elite Trainer Boxes", rank=1),
        _p(2, "Paldean Fates Elite Trainer Box", "Pokémon Elite Trainer Boxes", rank=2),
    ]
    hints = mod.token_hints(raw, products, exclude=set())
    assert hints[0]["id"] == 1
    assert hints[0]["coverage"] > hints[1]["coverage"]


# ── load_catalog ──────────────────────────────────────────────────────────────

def test_load_catalog_reads_jsonl_and_skips_blank_lines(mod, tmp_path):
    path = tmp_path / "curated.jsonl"
    path.write_text(
        json.dumps(_p(1, "Pitch Black Booster")) + "\n\n"
        + json.dumps(_p(2, "Chaos Rising Booster")) + "\n",
        encoding="utf-8",
    )
    assert [p["id"] for p in mod.load_catalog(path)] == [1, 2]


def test_load_catalog_exits_on_empty_file(mod, tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.load_catalog(path)


# ── --file parsing ────────────────────────────────────────────────────────────

def _run_cli(mod, monkeypatch, capsys, argv):
    monkeypatch.setattr("sys.argv", ["calibration_candidates.py", *argv])
    mod.main()
    return capsys.readouterr().out


@pytest.fixture()
def catalog_file(tmp_path):
    path = tmp_path / "curated.jsonl"
    path.write_text(
        json.dumps(_p(885547, "Pitch Black Booster", rank=3)) + "\n"
        + json.dumps(_p(885545, "Pitch Black Booster Box", "Pokémon Display", rank=1)) + "\n",
        encoding="utf-8",
    )
    return path


def test_cli_reads_name_sites_and_price_columns(mod, tmp_path, catalog_file, monkeypatch, capsys):
    names = tmp_path / "names.tsv"
    names.write_text("Pitch Black Booster\tPrisma\t5.95 EUR\n", encoding="utf-8")
    out = _run_cli(mod, monkeypatch, capsys, [str(catalog_file), "--file", str(names)])
    assert "Sites: Prisma" in out
    assert "Observed price: 5.95 EUR" in out


def test_cli_tolerates_a_name_only_file(mod, tmp_path, catalog_file, monkeypatch, capsys):
    names = tmp_path / "names.tsv"
    names.write_text("Pitch Black Booster\n\nPitch Black Booster Box\n", encoding="utf-8")
    out = _run_cli(mod, monkeypatch, capsys, [str(catalog_file), "--file", str(names)])
    assert "Calibration [1/2]" in out and "Calibration [2/2]" in out
    assert "Sites:" not in out


def test_cli_strips_stray_whitespace_around_fields(mod, tmp_path, catalog_file, monkeypatch, capsys):
    names = tmp_path / "names.tsv"
    names.write_text("  Pitch Black Booster \t Prisma \n", encoding="utf-8")
    out = _run_cli(mod, monkeypatch, capsys, [str(catalog_file), "--file", str(names)])
    # a trailing space on the raw_name would shift every difflib ratio
    assert "Calibration [1/1]: Pitch Black Booster\n" in out
    assert "Sites: Prisma\n" in out


def test_cli_requires_a_name_or_file(mod, monkeypatch, catalog_file):
    monkeypatch.setattr("sys.argv", ["calibration_candidates.py", str(catalog_file)])
    with pytest.raises(SystemExit):
        mod.main()


# ── render ────────────────────────────────────────────────────────────────────

def test_render_includes_ids_ranks_and_the_hint_section(mod):
    products = [
        _p(692088, "Scarlet & Violet Booster", rank=3),
        _p(728716, "Paradox Rift Booster", rank=25),
    ]
    out = mod.render("Scarlet &amp; Violet: Paradox Rift booster", 1, 25, "Peliparatiisi", products)
    assert "Calibration [1/25]" in out
    assert "Sites: Peliparatiisi" in out
    assert "(ID: 692088)" in out
    assert "rank 3" in out


def test_render_omits_hint_section_when_top_five_covers_everything(mod):
    products = [_p(1, "Pitch Black Booster", rank=1)]
    out = mod.render("Pitch Black Booster", 1, 1, "", products)
    assert "Also in catalog" not in out


# llm_calibrate.md's operator block mandates an observed-price line, so render
# has to be able to produce one.

def test_render_shows_observed_price_when_given(mod):
    products = [_p(1, "Pitch Black Booster", rank=1)]
    out = mod.render("Pitch Black Booster", 1, 1, "", products, price="5.95 EUR")
    assert "Observed price: 5.95 EUR" in out


def test_render_omits_price_line_when_absent(mod):
    products = [_p(1, "Pitch Black Booster", rank=1)]
    assert "Observed price" not in mod.render("Pitch Black Booster", 1, 1, "", products)
