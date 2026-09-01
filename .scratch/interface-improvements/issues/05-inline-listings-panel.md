# 05 — Inline listings panel

**What to build:** Clicking a row in the products table reveals a listings panel directly below the table. The panel shows every current listing for that product — one row per site — so the operator can compare prices, check stock, and click through to the exact product page without leaving the products view. An "Open detail page" button in the panel preserves access to the price-history chart.

**Products view (`app/views/products.py`):**

When `st.dataframe` returns a selected row (wired in ticket 04), the product's `id` is read from the selected row's data. `db.get_latest_price_per_site` is called with that `product_id` to fetch current listings. The panel renders below the dataframe using `st.dataframe` or a simple `st.columns` strip (whichever is cleaner for this fixed schema) with these columns per listing:

- Site name (text)
- Price (formatted number + currency)
- Stock status ("In stock" / "Out of stock" / "Unknown")
- Item link — direct product URL from `listings.product_url`, falling back to `sites.url`; rendered as a `LinkColumn` or `st.markdown` anchor
- Last seen (timestamp truncated to minute)

Below the per-listing rows, a single `st.button("Open detail page →")` pushes the product's id into `st.session_state["selected_product_id"]` and calls `st.rerun()` to navigate to the existing `show_detail` view.

Clicking a different row updates the panel to show that product's listings. Clicking the same row again (or clicking elsewhere to deselect) collapses the panel.

**`db.get_latest_price_per_site` update:**

The query already returns `site_name`, `site_url`, `price`, `currency`, `in_stock`, and `scraped_at`. It is extended to also return `product_url` by joining `listings` on `(site_id, raw_name)`.

**Blocked by:** 02 — Scraper: run tracking and listings persistence (listings data must exist), and 04 — Sortable products table with item links (the dataframe and row-selection wiring must exist).

**Status:** ready-for-agent

- [ ] Clicking a product row in the products table renders a listings panel below the table without navigating away.
- [ ] The panel shows one row per site that has a current reading for the product, with site name, price, stock status, item link, and last-seen time.
- [ ] The item link in the panel points to the direct product URL where available, and to the site homepage otherwise.
- [ ] Clicking "Open detail page →" in the panel navigates to the existing detail view with the price-history chart.
- [ ] Clicking a different row updates the panel to show that product's listings.
- [ ] When no row is selected the panel area is empty (no placeholder text required — absence is sufficient).
- [ ] The existing `show_detail` page and the "← Back to products" button within it continue to work correctly.
- [ ] `python -m pytest tests/` passes.
