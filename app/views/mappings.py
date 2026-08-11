import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Mapping Review")
st.write("Resolve undecided product name mappings. Select a product (or mark as junk) and the row saves immediately.")

# ── build dropdown options once per page load ─────────────────────────────────

NULL_OPTION = "— Not a Pokémon product"

@st.cache_data(ttl=60)
def build_dropdown_options(_conn_id: int) -> tuple[list[str], dict[str, int]]:
    """Returns (ordered label list, label→cardmarket id dict).
    NULL_OPTION maps to None (not included in the dict)."""
    products = db.get_cardmarket_products_for_dropdown(conn)
    labels: list[str] = [NULL_OPTION]
    label_to_id: dict[str, int] = {}

    current_cat = None
    for p in products:
        if p["category_name"] != current_cat:
            current_cat = p["category_name"]
            labels.append(f"── {current_cat} ──")  # non-selectable section header
        label = p["name"]
        # Deduplicate labels (same name can appear in different expansions)
        if label in label_to_id:
            label = f"{p['name']} (id {p['id']})"
        labels.append(label)
        label_to_id[label] = p["id"]

    return labels, label_to_id

options, label_to_id = build_dropdown_options(id(conn))

# ── load undecided rows ───────────────────────────────────────────────────────

undecided = db.get_undecided_mappings(conn)

if not undecided:
    st.success("No undecided mappings — queue is empty.")
    st.stop()

st.subheader(f"{len(undecided)} undecided name(s)")

# Column headers
c1, c2, c3, c4, c5 = st.columns([4, 2, 1, 2, 4])
c1.markdown("**Raw name**")
c2.markdown("**Sites**")
c3.markdown("**Readings**")
c4.markdown("**LLM suggestion**")
c5.markdown("**Map to**")
st.divider()

for row in undecided:
    raw_name: str = row["raw_name"]
    sites: str = row["sites"] or "—"
    reading_count: int = row["reading_count"] or 0
    suggestion_name: str | None = row["suggestion_name"]
    confidence: float | None = row["confidence"]

    # Work out the default dropdown index
    if suggestion_name and suggestion_name in label_to_id:
        default_idx = options.index(suggestion_name)
    else:
        default_idx = 0  # NULL_OPTION

    suggestion_text = (
        f"{suggestion_name} ({confidence:.0%})" if suggestion_name and confidence else "—"
    )

    def _on_change(rn: str = raw_name) -> None:
        chosen_label: str = st.session_state[f"map_{rn}"]
        if chosen_label.startswith("──"):
            return  # section header clicked — ignore
        cm_id: int | None = label_to_id.get(chosen_label)  # None for NULL_OPTION
        db.save_mapping(conn, rn, cm_id)
        st.cache_data.clear()

    col1, col2, col3, col4, col5 = st.columns([4, 2, 1, 2, 4])
    col1.write(raw_name)
    col2.write(sites)
    col3.write(str(reading_count))
    col4.write(suggestion_text)
    col5.selectbox(
        label="",
        options=options,
        index=default_idx,
        key=f"map_{raw_name}",
        label_visibility="collapsed",
        on_change=_on_change,
    )
