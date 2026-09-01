# 04 — Sortable products table with item links

**What to build:** The hand-rolled per-category products grid is replaced by a native Streamlit dataframe. Every column becomes click-sortable client-side. The "cheapest site" link becomes a direct link to the product page at that shop, falling back to the site homepage where no item URL is available. Category filtering replaces fixed subheaders.

**Products view (`app/views/products.py`):**

The `show_list()` function's inner loop and `st.subheader` grouping are removed. In their place, a single `st.dataframe` call renders the data with `column_config`:

| Column | Config | Notes |
|---|---|---|
| Name | `TextColumn` | canonical name |
| Category | `TextColumn` | also drives a `st.selectbox` filter above the table |
| Lowest price | `NumberColumn` | formatted to 2 decimal places |
| Item link | `LinkColumn` | direct product URL if available, site homepage otherwise |
| In stock | `TextColumn` | e.g. `"3 sites"` |
| Last updated | `TextColumn` | truncated to minute |

The dataframe is called with `selection_mode="single-row"` and `on_select="rerun"` so that row selection is wired for the listings panel (ticket 05). In this ticket, when a row is selected the area below the table shows a placeholder ("Select a product to see its listings") — the full panel is built in ticket 05.

**`db.get_products_summary` update:**

The query is extended to LEFT JOIN `listings` on `(site_id, raw_name)` for the cheapest listing, so it returns `product_url` alongside the existing fields. Where `product_url` is null or empty the UI falls back to `sites.url`.

**Blocked by:** 01 — Schema migration (the `listings` table must exist for the LEFT JOIN, even if empty).

**Status:** ready-for-agent

- [ ] The products view renders as a native dataframe — no `st.columns` loop, no `st.subheader` category groups.
- [ ] Clicking a column header sorts the table by that column; clicking again reverses the sort.
- [ ] A Category filter widget above the table narrows the displayed rows; selecting "All" shows every product.
- [ ] The Item link column renders as a clickable anchor. For listings where a `product_url` is stored in `listings`, the link points directly to the product page. For listings with no stored URL the link points to the site homepage.
- [ ] Row selection is wired: clicking a row selects it and the area below the table shows a placeholder message (the panel itself is in ticket 05).
- [ ] The "View" button column is removed; navigation to the detail page moves to the listings panel (ticket 05).
- [ ] The existing detail page (`show_detail`) and its price-history chart are unchanged and still reachable via the session-state mechanism.
- [ ] `get_products_summary` returns a `product_url` field; a test in `tests/test_db.py` asserts that this field is populated from `listings` when a row exists, and is `None` when no listing row exists.
- [ ] `python -m pytest tests/` passes.
