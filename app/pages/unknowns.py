import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Unknowns")
st.write("Raw names seen in price readings that have not yet been mapped to a canonical product.")

if flash := st.session_state.pop("_flash_unknowns", None):
    st.success(flash)

unmapped = db.get_unmapped_raw_names(conn)

if not unmapped:
    st.success("All raw names are mapped.")
    st.stop()

products = db.get_all_canonical_products(conn)
product_options = {p["canonical_name"]: p["id"] for p in products}
CREATE_NEW = "— Create new —"
selectbox_choices = [CREATE_NEW] + sorted(product_options.keys())

st.subheader(f"{len(unmapped)} unmapped name(s)")

col_raw, col_site, col_assign = st.columns([3, 2, 4])
col_raw.markdown("**Raw name**")
col_site.markdown("**Site**")
col_assign.markdown("**Map to**")
st.divider()

# Collect widget values; key=(raw_name, site_id)
assignments = {}
for row in unmapped:
    key = (row["raw_name"], row["site_id"])
    c1, c2, c3 = st.columns([3, 2, 4])
    c1.write(row["raw_name"])
    c2.write(row["site_name"])

    choice = c3.selectbox(
        label="",
        options=selectbox_choices,
        key=f"sel_{row['raw_name']}_{row['site_id']}",
        label_visibility="collapsed",
    )
    new_name = ""
    if choice == CREATE_NEW:
        new_name = c3.text_input(
            label="New canonical name",
            key=f"new_{row['raw_name']}_{row['site_id']}",
            label_visibility="collapsed",
            placeholder="Enter new canonical name…",
        )
    assignments[key] = {"choice": choice, "new_name": new_name}

st.divider()
if st.button("Save assignments", type="primary"):
    saved = 0
    for (raw_name, site_id), asgn in assignments.items():
        choice = asgn["choice"]
        if choice == CREATE_NEW:
            new_name = asgn["new_name"].strip()
            if not new_name:
                continue
            product_id = db.upsert_product(conn, new_name)
        else:
            product_id = product_options[choice]
        db.upsert_alias(conn, raw_name, site_id, product_id)
        saved += 1

    if saved:
        st.session_state["_flash_unknowns"] = f"Saved {saved} assignment(s)."
        st.rerun()
    else:
        st.warning("Nothing to save — select a product or enter a new name for each row.")
