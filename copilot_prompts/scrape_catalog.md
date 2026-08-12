# Cardmarket Catalog Scrape — Copilot browser prompt

Paste this prompt into a Copilot agentic browser session. It will navigate the 8 Cardmarket category pages, extract the popularity-ordered product list from each, and write the result to `catalog_scrape.json` in the project root.

**Re-run this quarterly, or whenever a major new Pokémon set releases.**

---

## Your task

Scrape the 8 Cardmarket sealed-Pokémon category pages listed below. For each page, extract every product entry in the order it appears (most popular first). Collect up to 10 pages per category (30 products per page = up to 300 products per category, ~2,400 total).

Save the combined result to a file called `catalog_scrape.json` in the project root directory.

---

## Step 1 — handle the captcha

Navigate to the first URL below. A captcha may appear. **Stop and wait for the operator to pass it manually.** Do not proceed until the product listing is visible on the page.

---

## Step 2 — scrape each category

Work through the 8 categories below **in order**. For each category:

1. Start at page 1 (the base URL).
2. Extract all product entries visible on the page (see "What to extract" below).
3. Construct the next page URL by appending `&site=N` (N = 2, 3, …) and navigate to it. Stop when the page returns zero product entries or you have completed 10 pages, whichever comes first.
5. Move on to the next category.

### The 8 categories

| Category name | Base URL (page 1) |
|---|---|
| Boosters | `https://www.cardmarket.com/en/Pokemon/Products/Boosters?searchMode=v2&idCategory=52&idExpansion=0&onlyAvailable=on&perSite=30` |
| Booster Boxes | `https://www.cardmarket.com/en/Pokemon/Products/Booster-Boxes?searchMode=v2&idCategory=53&idExpansion=0&onlyAvailable=on&perSite=30` |
| Theme Decks | `https://www.cardmarket.com/en/Pokemon/Products/Theme-Decks?searchMode=v2&idCategory=54&idExpansion=0&onlyAvailable=on&perSite=30` |
| Trainer Kits | `https://www.cardmarket.com/en/Pokemon/Products/Trainer-Kits?searchMode=v2&idCategory=1013&idExpansion=0&onlyAvailable=on&perSite=30` |
| Tins | `https://www.cardmarket.com/en/Pokemon/Products/Tins?searchMode=v2&idCategory=1014&idExpansion=0&onlyAvailable=on&perSite=30` |
| Box Sets | `https://www.cardmarket.com/en/Pokemon/Products/Box-Sets?searchMode=v2&idCategory=1015&idExpansion=0&onlyAvailable=on&perSite=30` |
| Elite Trainer Boxes | `https://www.cardmarket.com/en/Pokemon/Products/Elite-Trainer-Boxes?searchMode=v2&idCategory=1016&idExpansion=0&onlyAvailable=on&perSite=30` |
| Blisters | `https://www.cardmarket.com/en/Pokemon/Products/Blisters?searchMode=v2&idCategory=1083&idExpansion=0&onlyAvailable=on&perSite=30` |

**Pagination:** to go to page N, append `&site=N` to the base URL. For example, page 2 of Boosters is:
`https://www.cardmarket.com/en/Pokemon/Products/Boosters?searchMode=v2&idCategory=52&idExpansion=0&onlyAvailable=on&perSite=30&site=2`

---

## Step 3 — what to extract per product

Each product entry on the listing page is a card or row. Extract:

| Field | Where to find it |
|---|---|
| `cardmarket_product_id` | The integer product ID. Try these in order, stop at the first hit: (1) a numeric segment or `idProduct=` query parameter in the product link's `href`; (2) a `data-idproduct` or similar data attribute on the product card element; (3) the page's JSON-LD / structured data. If none of these expose the ID, write `null` — do not click through to individual product pages. |
| `name` | The product name as shown in the listing (e.g. `"Prismatic Evolutions Booster Pack"`). |
| `category` | The category name from the table above (e.g. `"Boosters"`). Use exactly the names in the table. |
| `popularity_rank` | The position of this product within its category, counting across all pages. The first product on page 1 is rank 1, the last product on page 10 is rank ≤ 300. |

---

## Step 4 — write the output file

Once all categories are scraped, write the results to `catalog_scrape.json` in the project root. The format is a JSON array, one object per product, in the order scraped (sorted by category then popularity_rank):

```json
[
  {
    "cardmarket_product_id": 271439,
    "name": "Prismatic Evolutions Booster Pack",
    "category": "Boosters",
    "popularity_rank": 1
  },
  {
    "cardmarket_product_id": 271440,
    "name": "Prismatic Evolutions Elite Trainer Box",
    "category": "Elite Trainer Boxes",
    "popularity_rank": 1
  }
]
```

If `cardmarket_product_id` could not be found for a product, write `null` for that field rather than omitting the entry.

---

## Step 5 — report

After writing the file, print a summary:

```
Scraped:
  Boosters:            N products (P pages)
  Booster Boxes:       N products (P pages)
  Theme Decks:         N products (P pages)
  Trainer Kits:        N products (P pages)
  Tins:                N products (P pages)
  Box Sets:            N products (P pages)
  Elite Trainer Boxes: N products (P pages)
  Blisters:            N products (P pages)
  ─────────────────────────────────────────
  Total:               N products
  Products with null cardmarket_product_id: N
```

---

## Notes

- **Do not scrape individual product pages** — only the category listing pages. Clicking through to 2,400 product pages would take too long.
- **`onlyAvailable=on`** — all URLs filter to currently-available products. `popularity_rank` therefore reflects position among available listings, not site-wide all-time popularity. This is intentional.
- **Duplicates across categories** — if the same product name appears in more than one category, include it once per category it appears in. Categories are distinct and the same product can legitimately be listed under multiple categories on Cardmarket.
- If a category has fewer than 30 products total, that is fine — just collect what is there.
- If Cardmarket shows a "no results" or empty page, stop pagination for that category.
- If another captcha appears mid-scrape, stop and wait for the operator to pass it before continuing.
- The scrape order within each category is the default Cardmarket sort (popularity). Do not re-sort.
