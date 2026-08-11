import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()

st.title("Categories")
st.caption("Categories come from the Cardmarket catalogue and are read-only. Use Mapping Review to assign raw names to products.")

rows = conn.execute("""
    SELECT
        cp.category_name,
        COUNT(DISTINCT cp.id) AS total_products,
        COUNT(DISTINCT nm.cardmarket_product_id) AS mapped_products
    FROM cardmarket_products cp
    LEFT JOIN name_mappings nm
        ON nm.cardmarket_product_id = cp.id AND nm.status = 'mapped'
    GROUP BY cp.category_name
    ORDER BY mapped_products DESC, cp.category_name
""").fetchall()

if not rows:
    st.info("No categories in catalogue.")
    st.stop()

h1, h2, h3 = st.columns([4, 2, 2])
h1.markdown("**Category**")
h2.markdown("**Products in catalogue**")
h3.markdown("**Products with mappings**")
st.divider()

for row in rows:
    c1, c2, c3 = st.columns([4, 2, 2])
    c1.write(row["category_name"] or "—")
    c2.write(str(row["total_products"]))
    c3.write(str(row["mapped_products"]))
