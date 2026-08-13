"""Tests for scripts/extract_catalog.py."""
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "extract_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_catalog", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_module()


# ── fold ──────────────────────────────────────────────────────────────────────
# Cardmarket's URL slugs drop some punctuation entirely ("McDonald's" -> "McDonalds",
# "CSV9.5C" -> "CSV95C") and turn other runs into hyphens. Folding both the slug and
# the catalogue name down to bare alphanumerics makes the two forms comparable.

def test_fold_keeps_only_lowercase_alphanumerics(mod):
    assert mod.fold("Base Set Booster") == "basesetbooster"


def test_fold_drops_apostrophes(mod):
    assert mod.fold("McDonald's Collection 25th Anniversary Booster") == \
        "mcdonaldscollection25thanniversarybooster"


def test_fold_drops_decimal_points(mod):
    assert mod.fold("CSV9.5C: Terastal Gathering Booster") == "csv95cterastalgatheringbooster"


def test_fold_folds_diacritics_to_ascii(mod):
    assert mod.fold("Poké Ball Tin") == "pokeballtin"


def test_fold_maps_slug_and_catalogue_name_to_the_same_key(mod):
    assert mod.fold("Champions-Path-Booster") == mod.fold("Champion's Path Booster")


# ── parse_catalog_dump ────────────────────────────────────────────────────────

DUMP = """=== Boosters | page 1 ===
- link "Destined Rivals Booster": /url: /en/Pokemon/Products/Boosters/Destined-Rivals-Booster
- link "Base Set Booster": /url: /en/Pokemon/Products/Boosters/Base-Set-Booster

=== Boosters | page 2 ===
- link "Jungle Booster": /url: /en/Pokemon/Products/Boosters/Jungle-Booster
"""


def test_parse_catalog_dump_returns_slugs_in_page_order(mod):
    entries, pages = mod.parse_catalog_dump(DUMP)
    assert [e.slug for e in entries] == ["Destined-Rivals-Booster", "Base-Set-Booster", "Jungle-Booster"]
    assert pages == 2


def test_parse_catalog_dump_captures_the_link_label(mod):
    entries, _ = mod.parse_catalog_dump(DUMP)
    assert entries[0].label == "Destined Rivals Booster"


def test_parse_catalog_dump_ignores_blank_and_unrecognised_lines(mod):
    entries, pages = mod.parse_catalog_dump(
        '=== Tins | page 1 ===\n\nsome noise\n- link "A Tin": /url: /en/Pokemon/Products/Tins/A-Tin\n'
    )
    assert [e.slug for e in entries] == ["A-Tin"]
    assert pages == 1


def test_parse_catalog_dump_takes_the_last_path_segment_as_the_slug(mod):
    entries, _ = mod.parse_catalog_dump(
        '=== Tins | page 1 ===\n- link "A": /url: /en/Pokemon/Products/Tins/Deep/Nested-Slug\n'
    )
    assert entries[0].slug == "Nested-Slug"


# ── clean_label ───────────────────────────────────────────────────────────────
# Listing labels sometimes prepend the expansion name to the product name, so the
# label arrives with its opening phrase repeated.

def test_clean_label_drops_a_repeated_opening_phrase(mod):
    assert mod.clean_label("BREAKthrough BREAKthrough Elite Trainer Box (Mega Mewtwo X)") == \
        "BREAKthrough Elite Trainer Box (Mega Mewtwo X)"


def test_clean_label_halves_a_fully_duplicated_label(mod):
    assert mod.clean_label("EX Trainer Kit EX Trainer Kit") == "EX Trainer Kit"


def test_clean_label_leaves_an_ordinary_label_untouched(mod):
    assert mod.clean_label("Destined Rivals Booster") == "Destined Rivals Booster"


# ── build_index / resolve_category ────────────────────────────────────────────

CATALOGUE = [
    {"idProduct": 271823, "name": "Base Set Booster", "idCategory": 52},
    {"idProduct": 271824, "name": "Base Set Booster Box", "idCategory": 53},
    {"idProduct": 400001, "name": "Champion's Path Booster", "idCategory": 52},
    # Same name twice under one category — a real quirk of the export.
    {"idProduct": 585743, "name": "Golisopod Stage 1 Blister", "idCategory": 1083},
    {"idProduct": 585733, "name": "Golisopod Stage 1 Blister", "idCategory": 1083},
    # Products whose slug omits or mangles part of the real name.
    {"idProduct": 362931, "name": "Generic Poké Ball Tin", "idCategory": 1014},
    {"idProduct": 585663, "name": "Fusion Strike: Blitzle 1-Pack Blister", "idCategory": 1083},
    {"idProduct": 900001, "name": "Booster", "idCategory": 52},
]

def test_build_index_keys_products_by_category_and_folded_name(mod):
    index = mod.build_index(CATALOGUE)
    assert [p["idProduct"] for p in index[(52, "basesetbooster")]] == [271823]


def test_build_index_keeps_same_named_products_together_lowest_id_first(mod):
    index = mod.build_index(CATALOGUE)
    assert [p["idProduct"] for p in index[(1083, "golisopodstage1blister")]] == [585733, 585743]


def _boosters(mod):
    return mod.Category(name="Boosters", id_category=52)


def test_resolve_category_matches_a_slug_to_its_product_id(mod):
    entries = [mod.Entry(slug="Base-Set-Booster", label="Base Set Booster")]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records == [{
        "cardmarket_product_id": 271823,
        "name": "Base Set Booster",
        "category": "Boosters",
        "popularity_rank": 1,
    }]
    assert stats.matched == 1


def test_resolve_category_matches_across_dropped_punctuation(mod):
    entries = [mod.Entry(slug="Champions-Path-Booster", label="Champion's Path Booster")]
    records, _ = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["cardmarket_product_id"] == 400001


def test_resolve_category_uses_the_canonical_catalogue_name_over_the_label(mod):
    entries = [mod.Entry(slug="Champions-Path-Booster", label="Champions Path Champions Path Booster")]
    records, _ = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["name"] == "Champion's Path Booster"


def test_resolve_category_ranks_products_sequentially_in_listing_order(mod):
    entries = [
        mod.Entry(slug="Champions-Path-Booster", label="Champion's Path Booster"),
        mod.Entry(slug="Base-Set-Booster", label="Base Set Booster"),
    ]
    records, _ = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert [(r["cardmarket_product_id"], r["popularity_rank"]) for r in records] == \
        [(400001, 1), (271823, 2)]


def test_resolve_category_drops_repeats_without_leaving_a_rank_gap(mod):
    # Consecutive scrape pages overlapped by one product, so the dump repeats it.
    entries = [
        mod.Entry(slug="Base-Set-Booster", label="Base Set Booster"),
        mod.Entry(slug="Base-Set-Booster", label="Base Set Booster"),
        mod.Entry(slug="Champions-Path-Booster", label="Champion's Path Booster"),
    ]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert [(r["cardmarket_product_id"], r["popularity_rank"]) for r in records] == \
        [(271823, 1), (400001, 2)]
    assert stats.duplicates == 1


def test_resolve_category_ignores_products_from_other_categories(mod):
    # "Base Set Booster Box" exists, but only under category 53.
    entries = [mod.Entry(slug="Base-Set-Booster-Box", label="Base Set Booster Box")]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["cardmarket_product_id"] is None
    assert stats.unresolved == 1


def test_resolve_category_keeps_unmatched_products_with_a_null_id(mod):
    entries = [mod.Entry(slug="Brand-New-Set-Booster", label="Brand New Set Booster")]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records == [{
        "cardmarket_product_id": None,
        "name": "Brand New Set Booster",
        "category": "Boosters",
        "popularity_rank": 1,
    }]
    assert stats.unresolved == 1


# The listing label is expansion name + product name, so when a slug is unusable the
# real catalogue name is recoverable as a trailing run of the label's words.

def test_resolve_category_falls_back_to_the_label_when_the_slug_omits_a_word(mod):
    # Slug drops "Generic", so only the label can resolve it.
    entries = [mod.Entry(slug="Poke-Ball-Tin", label="Pokémon Products Generic Poké Ball Tin")]
    tins = mod.Category(name="Tins", id_category=1014)
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), tins)
    assert records[0]["cardmarket_product_id"] == 362931
    assert records[0]["name"] == "Generic Poké Ball Tin"
    assert stats.rescued == 1
    assert stats.matched == 1
    assert stats.unresolved == 0


def test_resolve_category_falls_back_to_the_label_when_the_slug_is_a_templating_bug(mod):
    entries = [mod.Entry(
        slug="LocExpansionName-Blitzle-1-Pack-Blister",
        label="Fusion Strike Fusion Strike: Blitzle 1-Pack Blister",
    )]
    blisters = mod.Category(name="Blisters", id_category=1083)
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), blisters)
    assert records[0]["cardmarket_product_id"] == 585663
    assert stats.rescued == 1


def test_resolve_category_prefers_the_slug_over_the_label(mod):
    # A correct slug must win even if the label would also resolve to something.
    entries = [mod.Entry(slug="Base-Set-Booster", label="Champion's Path Booster")]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["cardmarket_product_id"] == 271823
    assert stats.rescued == 0


def test_resolve_category_label_fallback_ignores_one_word_suffixes(mod):
    # "Booster" alone is a real catalogue row; matching it off a trailing word would
    # attach an unrelated id to anything ending in "Booster".
    entries = [mod.Entry(slug="Totally-New-Set-Booster", label="Totally New Set Booster")]
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["cardmarket_product_id"] is None
    assert stats.unresolved == 1


def test_resolve_category_label_fallback_takes_the_longest_matching_suffix(mod):
    entries = [mod.Entry(slug="No-Such-Slug", label="Extra Words Base Set Booster")]
    records, _ = mod.resolve_category(entries, mod.build_index(CATALOGUE), _boosters(mod))
    assert records[0]["cardmarket_product_id"] == 271823


def test_resolve_category_breaks_ambiguous_matches_on_the_lowest_product_id(mod):
    entries = [mod.Entry(slug="Golisopod-Stage-1-Blister", label="Golisopod Stage 1 Blister")]
    blisters = mod.Category(name="Blisters", id_category=1083)
    records, stats = mod.resolve_category(entries, mod.build_index(CATALOGUE), blisters)
    assert records[0]["cardmarket_product_id"] == 585733
    assert stats.ambiguous == 1
    assert stats.matched == 1


# ── header_categories ─────────────────────────────────────────────────────────

def test_header_categories_reads_the_category_from_page_headers(mod):
    assert mod.header_categories(DUMP) == {"Boosters"}


# ── extract ───────────────────────────────────────────────────────────────────

def test_extract_concatenates_categories_and_ranks_each_independently(mod):
    boosters = '=== Boosters | page 1 ===\n- link "Base Set Booster": /url: /x/Base-Set-Booster\n'
    boxes = '=== Booster Boxes | page 1 ===\n- link "Base Set Booster Box": /url: /x/Base-Set-Booster-Box\n'
    sources = [
        (mod.Category("Boosters", 52), boosters),
        (mod.Category("Booster Boxes", 53), boxes),
    ]
    records, stats = mod.extract(sources, CATALOGUE)
    assert [(r["category"], r["cardmarket_product_id"], r["popularity_rank"]) for r in records] == [
        ("Boosters", 271823, 1),
        ("Booster Boxes", 271824, 1),
    ]
    assert stats["Boosters"].pages == 1


def test_extract_rejects_a_dump_whose_headers_name_another_category(mod):
    mislabelled = '=== Tins | page 1 ===\n- link "A Tin": /url: /x/A-Tin\n'
    with pytest.raises(ValueError, match="Tins"):
        mod.extract([(mod.Category("Boosters", 52), mislabelled)], CATALOGUE)


def test_extract_tolerates_a_dump_with_no_page_headers(mod):
    records, _ = mod.extract(
        [(mod.Category("Boosters", 52), '- link "Base Set Booster": /url: /x/Base-Set-Booster\n')],
        CATALOGUE,
    )
    assert records[0]["cardmarket_product_id"] == 271823


# ── load_catalogue ────────────────────────────────────────────────────────────

def test_load_catalogue_returns_the_products_array(mod, tmp_path):
    path = tmp_path / "cat.json"
    path.write_text('{"version": 1, "products": [{"idProduct": 1, "name": "A", "idCategory": 52}]}')
    assert mod.load_catalogue(path) == [{"idProduct": 1, "name": "A", "idCategory": 52}]
