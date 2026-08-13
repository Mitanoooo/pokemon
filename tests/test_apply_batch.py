"""Tests for scripts/apply_batch.py accumulate mode.

Only accumulate mode is covered — finalize mode shells out to Hetzner over SSH.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "apply_batch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("apply_batch", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    m = _load_module()
    monkeypatch.setattr(m, "DRAFT_FILE", tmp_path / "draft_mappings.json")
    return m


def _write_csv(tmp_path, text):
    path = tmp_path / "batch_001.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _draft(mod):
    return json.loads(mod.DRAFT_FILE.read_text(encoding="utf-8"))


def test_accumulate_writes_expected_entry_shape(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status\n"
        "Pitch Black Booster Box,Pitch Black Booster Box,885545,0.95,mapped\n",
    )
    mod.accumulate(csv_path)
    assert _draft(mod) == [
        {
            "raw_name": "Pitch Black Booster Box",
            "proposed_name": "Pitch Black Booster Box",
            "cardmarket_product_id": 885545,
            "confidence": 0.95,
            "status": "mapped",
        }
    ]


# ── extra columns ─────────────────────────────────────────────────────────────
# llm_batch_normalise.md emits a trailing `observed_price` column so the operator
# can spot a pack mapped to a display box during review. It is review-only and
# must not reach draft_mappings.json.

def test_accumulate_ignores_observed_price_column(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status,observed_price\n"
        "Destined Rivals Booster laatikko,Destined Rivals Booster Box,818574,0.93,mapped,389.50\n",
    )
    mod.accumulate(csv_path)
    (entry,) = _draft(mod)
    assert "observed_price" not in entry
    assert entry["cardmarket_product_id"] == 818574


def test_accumulate_ignores_any_unknown_column(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status,sites,notes\n"
        "Pokemon ME04 Booster,Chaos Rising Booster,877296,0.9,mapped,JR,checked\n",
    )
    mod.accumulate(csv_path)
    (entry,) = _draft(mod)
    assert set(entry) == {
        "raw_name",
        "proposed_name",
        "cardmarket_product_id",
        "confidence",
        "status",
    }


# ── null_mapped / undecided rows ───────────────────────────────────────────────

def test_accumulate_maps_empty_id_and_confidence_to_none(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status,observed_price\n"
        "Topps Formula 1 Turbo Attax Eco Box 2025,,,0.97,null_mapped,7.19\n"
        "Pokemon Deck Champ World,,,0.4,undecided,32.95\n",
    )
    mod.accumulate(csv_path)
    rows = _draft(mod)
    assert [r["cardmarket_product_id"] for r in rows] == [None, None]
    assert [r["status"] for r in rows] == ["null_mapped", "undecided"]


def test_accumulate_keeps_best_guess_id_on_undecided(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status,observed_price\n"
        "Pokemon Lumiose City Mini Tin,Lumiose City: Feraligatr Mini Tin,878509,0.5,undecided,14.90\n",
    )
    mod.accumulate(csv_path)
    (entry,) = _draft(mod)
    assert entry["cardmarket_product_id"] == 878509
    assert entry["status"] == "undecided"


# ── accumulate is keyed on raw_name ───────────────────────────────────────────
# Re-running a corrected CSV must overwrite cleanly rather than duplicate.

def test_accumulate_overwrites_by_raw_name(mod, tmp_path, capsys):
    header = "raw_name,proposed_name,cardmarket_product_id,confidence,status\n"
    mod.accumulate(_write_csv(tmp_path, header + "X,Wrong Product,111,0.9,mapped\n"))
    capsys.readouterr()

    mod.accumulate(_write_csv(tmp_path, header + "X,Right Product,222,0.95,mapped\n"))
    out = capsys.readouterr().out

    (entry,) = _draft(mod)
    assert entry["proposed_name"] == "Right Product"
    assert entry["cardmarket_product_id"] == 222
    assert "Rows added:       0" in out
    assert "Rows overwritten: 1" in out


def test_accumulate_appends_new_names_to_existing_draft(mod, tmp_path):
    header = "raw_name,proposed_name,cardmarket_product_id,confidence,status\n"
    mod.accumulate(_write_csv(tmp_path, header + "A,First,1,0.9,mapped\n"))
    mod.accumulate(_write_csv(tmp_path, header + "B,Second,2,0.9,mapped\n"))
    assert [r["raw_name"] for r in _draft(mod)] == ["A", "B"]


def test_accumulate_preserves_non_ascii_raw_names(mod, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "raw_name,proposed_name,cardmarket_product_id,confidence,status\n"
        "Pokemon Keräilykortit Chaos Rising Boosterpakkaus,Chaos Rising Booster,877296,0.92,mapped\n",
    )
    mod.accumulate(csv_path)
    (entry,) = _draft(mod)
    assert entry["raw_name"] == "Pokemon Keräilykortit Chaos Rising Boosterpakkaus"
