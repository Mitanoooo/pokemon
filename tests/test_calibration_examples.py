"""Structural checks on copilot_prompts/calibration_examples.md.

The file is read verbatim as few-shot context by llm_batch_normalise.md (Step 4),
so its shape is a contract: llm_calibrate.md fixes the per-example fields, and the
batch prompt cites examples by number. These tests guard against an edit that
drops a field or renumbers the bank.
"""
import re
from pathlib import Path

import pytest

_DOC = Path(__file__).parent.parent / "copilot_prompts" / "calibration_examples.md"
_EXPECTED_EXAMPLES = 25
_VALID_STATUSES = {"mapped", "null_mapped", "undecided"}


@pytest.fixture(scope="module")
def doc():
    return _DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def examples(doc):
    """Split the document into per-example bodies, keyed by example number."""
    parts = re.split(r"^## Example (\d+)$", doc, flags=re.MULTILINE)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def test_header_declares_the_example_count(doc):
    assert doc.startswith("# Calibration Examples")
    assert f"Total: {_EXPECTED_EXAMPLES} examples" in doc


def test_bank_has_the_expected_number_of_examples(examples):
    assert len(examples) == _EXPECTED_EXAMPLES


def test_examples_are_numbered_contiguously_from_one(examples):
    assert sorted(examples) == list(range(1, _EXPECTED_EXAMPLES + 1))


@pytest.mark.parametrize(
    "field",
    [
        "**raw_name:**",
        "**Candidates shown:**",
        "**Chosen mapping:**",
        "**Status:**",
        "**Why it matched:**",
        "**Why candidates didn't match:**",
    ],
)
def test_every_example_carries_each_required_field(examples, field):
    missing = [n for n, body in examples.items() if field not in body]
    assert missing == [], f"{field} missing from examples {missing}"


def test_every_example_declares_a_valid_status(examples):
    for n, body in examples.items():
        statuses = re.findall(r"\*\*Status:\*\* `(\w+)`", body)
        assert len(statuses) == 1, f"example {n} has {len(statuses)} Status lines"
        assert statuses[0] in _VALID_STATUSES, f"example {n}: bad status {statuses[0]!r}"


def test_every_example_lists_five_candidates(examples):
    for n, body in examples.items():
        block = body.split("**Candidates shown:**")[1].split("**Chosen mapping:**")[0]
        numbered = re.findall(r"^(\d+)\. ", block, flags=re.MULTILINE)
        assert numbered == ["1", "2", "3", "4", "5"], f"example {n} candidates: {numbered}"


def test_every_candidate_carries_an_id_category_rank_and_score(examples):
    for n, body in examples.items():
        block = body.split("**Candidates shown:**")[1].split("**Chosen mapping:**")[0]
        for line in [ln for ln in block.splitlines() if re.match(r"^\d+\. ", ln)]:
            assert re.search(r"\(ID: \d+\) — .+, rank \d+, score [\d.]+$", line), \
                f"example {n}: malformed candidate line {line!r}"


def test_every_example_gives_a_reason_per_shown_candidate(examples):
    for n, body in examples.items():
        shown = body.split("**Candidates shown:**")[1].split("**Chosen mapping:**")[0]
        reasons = body.split("**Why candidates didn't match:**")[1]
        n_shown = len(re.findall(r"^\d+\. ", shown, flags=re.MULTILINE))
        n_reasons = len(re.findall(r"^- ", reasons, flags=re.MULTILINE))
        assert n_shown == n_reasons, f"example {n}: {n_shown} candidates but {n_reasons} reasons"


# ── mapped rows must name a product id; the other statuses need not ────────────

def test_mapped_examples_name_a_product_id(examples):
    for n, body in examples.items():
        chosen = re.search(r"\*\*Chosen mapping:\*\* (.+)", body).group(1)
        status = re.search(r"\*\*Status:\*\* `(\w+)`", body).group(1)
        if status == "mapped":
            assert re.search(r"\(ID: \d+\)", chosen), f"example {n} is mapped but names no id"


def test_null_mapped_examples_choose_none(examples):
    for n, body in examples.items():
        chosen = re.search(r"\*\*Chosen mapping:\*\* (.+)", body).group(1)
        status = re.search(r"\*\*Status:\*\* `(\w+)`", body).group(1)
        if status == "null_mapped":
            assert "`none`" in chosen, f"example {n} is null_mapped but names a product"


# ── the bank must exercise all three statuses, or it teaches nothing ──────────

def test_bank_covers_every_status(examples):
    found = {re.search(r"\*\*Status:\*\* `(\w+)`", b).group(1) for b in examples.values()}
    assert found == _VALID_STATUSES


def test_operator_decision_rules_are_documented(doc):
    assert "## Operator decision rules" in doc
    # llm_batch_normalise.md section 5b2 mirrors these; both cite example numbers.
    for cited in ("example 11", "examples 9 and 10"):
        assert cited in doc
