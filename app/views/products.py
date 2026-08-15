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
        "SELECT name FROM cardmarket_products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product:
        st.error("Product not found.")
        return

    st.title(product["name"])
    if st.button("← Back to products"):
        st.session_state.pop("selected_product_id", None)
        st.rerun()

    # Current prices per site
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
            link = r.get("product_url") or r["site_url"]
            rows.append({
                "Site": r["site_name"],
                "Price": price_str,
                "Stock": stock,
                "Link": link,
                "Last updated": str(r["scraped_at"] or "")[:16],
            })
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={"Link": st.column_config.LinkColumn("Link")},
            use_container_width=True,
            hide_index=True,
        )
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


# ── listings panel ───────────────────────────────────────────────────────────

def _show_listings_panel(product_id: int, product_name: str) -> None:
    st.subheader(f"Listings — {product_name}")

    listings = db.get_latest_price_per_site(conn, product_id)
    if not listings:
        st.info("No listings data for this product.")
    else:
        rows = []
        for r in listings:
            price_str = f"{r['price']:.2f} {r['currency']}" if r["price"] else "—"
            if r["in_stock"] is None:
                stock = "Unknown"
            elif r["in_stock"]:
                stock = "In stock"
            else:
                stock = "Out of stock"
            link = r.get("product_url") or r.get("site_url") or ""
            rows.append({
                "Site": r["site_name"],
                "Price": price_str,
                "Stock": stock,
                "Link": link,
                "Last seen": str(r["scraped_at"] or "")[:16],
            })
        st.dataframe(
            pd.DataFrame(rows),
            column_config={"Link": st.column_config.LinkColumn("Link")},
            use_container_width=True,
            hide_index=True,
        )

    if st.button("Open detail page →"):
        st.session_state["selected_product_id"] = product_id
        st.rerun()


# ── list view ────────────────────────────────────────────────────────────────

def show_list() -> None:
    st.title("Products")

    rows = db.get_products_summary(conn)
    if not rows:
        st.info("No products yet.")
        return

    df = pd.DataFrame(rows).reset_index(drop=True)

    # Category filter
    all_cats = sorted([c for c in df["category"].unique() if c != "Uncategorised"])
    if "Uncategorised" in df["category"].values:
        all_cats.append("Uncategorised")
    selected_cat = st.selectbox("Category", ["All"] + all_cats)

    if selected_cat != "All":
        df = df[df["category"] == selected_cat].reset_index(drop=True)

    # Build display dataframe
    display_df = pd.DataFrame({
        "Name": df["canonical_name"],
        "Category": df["category"],
        "Lowest price": df["lowest_price"],
        "Item link": df.apply(
            lambda r: r.get("product_url") or r.get("cheapest_site_url") or "",
            axis=1,
        ),
        "In stock": df["sites_in_stock"].apply(
            lambda n: f"{int(n)} site(s)" if n else "0 sites"
        ),
        "Last updated": df["last_updated"].apply(
            lambda t: str(t or "Never")[:16]
        ),
        "_id": df["id"],
    })

    event = st.dataframe(
        display_df.drop(columns=["_id"]),
        column_config={
            "Name": st.column_config.TextColumn("Name"),
            "Category": st.column_config.TextColumn("Category"),
            "Lowest price": st.column_config.NumberColumn("Lowest price", format="%.2f"),
            "Item link": st.column_config.LinkColumn("Item link"),
            "In stock": st.column_config.TextColumn("In stock"),
            "Last updated": st.column_config.TextColumn("Last updated"),
        },
        selection_mode="single-row",
        on_select="rerun",
        use_container_width=True,
        hide_index=True,
    )

    selected_rows = event.selection.rows
    if selected_rows:
        idx = selected_rows[0]
        product_id = int(display_df.iloc[idx]["_id"])
        product_name = str(display_df.iloc[idx]["Name"])
        _show_listings_panel(product_id, product_name)


# ── router ───────────────────────────────────────────────────────────────────

selected = st.session_state.get("selected_product_id")
if selected is not None:
    show_detail(selected)
else:
    show_list()
