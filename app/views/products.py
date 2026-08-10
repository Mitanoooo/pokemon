import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper import db

conn = st.session_state.get("conn")
if conn is None:
    st.error("No database connection.")
    st.stop()


# ── detail view ──────────────────────────────────────────────────────────────

def show_detail(product_id: int) -> None:
    product = conn.execute(
        "SELECT canonical_name FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product:
        st.error("Product not found.")
        return

    st.title(product["canonical_name"])
    if st.button("← Back to products"):
        st.session_state.pop("selected_product_id", None)
        st.rerun()

    # Current prices per site (reuse existing db helper)
    current = db.get_latest_price_per_site(conn, product_id)
    st.subheader("Current prices")
    if current:
        rows = []
        for r in current:
            price_str = f"{r['price']:.2f} {r['currency']}"
            if r["in_stock"] is None:
                stock = "Unknown"
            elif r["in_stock"]:
                stock = "In stock"
            else:
                stock = "Out of stock"
            site_link = f"[{r['site_name']}]({r['site_url']})"
            rows.append({
                "Site": site_link,
                "Price": price_str,
                "Stock": stock,
                "Last updated": r["scraped_at"],
            })
        df = pd.DataFrame(rows)
        st.markdown(df.to_markdown(index=False), unsafe_allow_html=True)
    else:
        st.info("No price data for this product.")

    # Price history chart
    history = db.get_product_price_history(conn, product_id)
    if history:
        st.subheader("Price history")
        df_hist = pd.DataFrame(history)
        df_hist["scraped_at"] = pd.to_datetime(df_hist["scraped_at"])
        currencies = df_hist["currency"].unique()
        if len(currencies) == 1:
            df_hist["label"] = df_hist["site_name"]
        else:
            df_hist["label"] = df_hist["site_name"] + " (" + df_hist["currency"] + ")"

        pivot = df_hist.pivot_table(
            index="scraped_at", columns="label", values="price", aggfunc="mean"
        )
        st.line_chart(pivot)


# ── list view ────────────────────────────────────────────────────────────────

def show_list() -> None:
    st.title("Products")

    rows = db.get_products_summary(conn)

    if not rows:
        st.info("No products yet.")
        return

    df = pd.DataFrame(rows)

    categories = sorted(
        [c for c in df["category"].unique() if c != "Uncategorised"]
    ) + (["Uncategorised"] if "Uncategorised" in df["category"].values else [])

    # Column header
    hcol1, hcol2, hcol3, hcol4, hcol5, hcol6, _ = st.columns([3, 2, 2, 2, 2, 1, 1])
    hcol1.markdown("**Name**")
    hcol2.markdown("**Category**")
    hcol3.markdown("**Lowest price**")
    hcol4.markdown("**Cheapest site**")
    hcol5.markdown("**In stock**")
    hcol6.markdown("**Last updated**")
    st.divider()

    for cat in categories:
        group = df[df["category"] == cat].sort_values("lowest_price", na_position="last")
        st.subheader(cat)

        for _, row in group.iterrows():
            price_display = (
                f"{row['lowest_price']:.2f} {row['currency']}"
                if pd.notna(row["lowest_price"])
                else "—"
            )
            site_display = (
                f"[{row['cheapest_site']}]({row['cheapest_site_url']})"
                if row["cheapest_site"]
                else "—"
            )
            in_stock_display = (
                f"{int(row['sites_in_stock'])} site(s)"
                if row["sites_in_stock"]
                else "0 sites"
            )
            last_updated = str(row["last_updated"] or "Never")

            col1, col2, col3, col4, col5, col6, col7 = st.columns([3, 2, 2, 2, 2, 1, 1])
            col1.write(row["canonical_name"])
            col2.write(row["category"])
            col3.write(price_display)
            col4.markdown(site_display, unsafe_allow_html=True)
            col5.write(in_stock_display)
            col6.write(last_updated[:16] if last_updated != "Never" else "Never")
            if col7.button("View", key=f"view_{row['id']}"):
                st.session_state["selected_product_id"] = int(row["id"])
                st.rerun()


# ── router ───────────────────────────────────────────────────────────────────

selected = st.session_state.get("selected_product_id")
if selected is not None:
    show_detail(selected)
else:
    show_list()
