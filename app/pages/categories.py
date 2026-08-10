import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Categories")

if flash := st.session_state.pop("_flash_categories", None):
    st.success(flash)

# ── existing categories + rename ─────────────────────────────────────────────

st.subheader("Existing categories")
categories = db.get_all_categories(conn)

if not categories:
    st.info("No categories yet.")
else:
    renames = {}
    for cat in categories:
        new_name = st.text_input(
            label=f"cat_{cat['id']}",
            value=cat["name"],
            key=f"rename_{cat['id']}",
            label_visibility="collapsed",
        )
        renames[cat["id"]] = new_name

    if st.button("Save renames"):
        updated = 0
        for cat in categories:
            new_name = renames[cat["id"]].strip()
            if new_name and new_name != cat["name"]:
                db.rename_category(conn, cat["id"], new_name)
                updated += 1
        if updated:
            st.session_state["_flash_categories"] = f"Renamed {updated} category/categories."
            st.rerun()
        else:
            st.info("No changes to save.")

st.divider()

# ── add new category ──────────────────────────────────────────────────────────

st.subheader("New category")
col_new, col_btn = st.columns([3, 1])
new_cat_name = col_new.text_input(
    "New category name",
    key="new_cat_name",
    label_visibility="collapsed",
    placeholder="Category name…",
)
if col_btn.button("Add"):
    name = new_cat_name.strip()
    if not name:
        st.warning("Enter a category name.")
    else:
        existing = [c["name"] for c in categories]
        if name in existing:
            st.warning(f"Category '{name}' already exists.")
        else:
            db.add_category(conn, name)
            st.session_state["_flash_categories"] = f"Added category '{name}'."
            st.rerun()

st.divider()

# ── reassign product categories ───────────────────────────────────────────────

st.subheader("Product categories")
products = db.get_all_canonical_products(conn)

if not products:
    st.info("No products yet.")
    st.stop()

categories = db.get_all_categories(conn)  # re-fetch after possible add
UNCAT = "Uncategorised"
cat_name_to_id = {c["name"]: c["id"] for c in categories}
cat_id_to_name = {c["id"]: c["name"] for c in categories}
cat_options = [UNCAT] + sorted(cat_name_to_id.keys())

reassign = {}

col_p, col_c = st.columns([3, 3])
col_p.markdown("**Product**")
col_c.markdown("**Category**")
st.divider()

for p in products:
    current_name = cat_id_to_name.get(p["category_id"], UNCAT)
    idx = cat_options.index(current_name) if current_name in cat_options else 0

    c1, c2 = st.columns([3, 3])
    c1.write(p["canonical_name"])
    selected = c2.selectbox(
        label="",
        options=cat_options,
        index=idx,
        key=f"pcat_{p['id']}",
        label_visibility="collapsed",
    )
    reassign[p["id"]] = selected

st.divider()
if st.button("Save category assignments", type="primary"):
    changed = 0
    for p in products:
        selected_name = reassign[p["id"]]
        new_cat_id = cat_name_to_id.get(selected_name)  # None for Uncategorised
        if new_cat_id != p["category_id"]:
            db.set_product_category(conn, p["id"], new_cat_id)
            changed += 1
    if changed:
        st.session_state["_flash_categories"] = f"Updated {changed} product(s)."
        st.rerun()
    else:
        st.info("No changes to save.")
