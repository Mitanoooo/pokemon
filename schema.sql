CREATE TABLE IF NOT EXISTS sites (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    url                  TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    last_scraped_at      TEXT,
    last_error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    null_price_count     INTEGER NOT NULL DEFAULT 0
);

-- Imported once from cardmarket_catalogue.json; never written by the scraper.
CREATE TABLE IF NOT EXISTS cardmarket_products (
    id            INTEGER PRIMARY KEY,  -- cardmarket idProduct
    name          TEXT NOT NULL,
    id_category   INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    id_expansion  INTEGER NOT NULL,
    date_added    TEXT
);

-- One row per distinct raw_name seen across all scraped sites.
-- status: 'mapped'      → cardmarket_product_id is set (confident match or manual)
--         'null_mapped' → confirmed not a tracked product; ignore everywhere
--         'undecided'   → below-threshold LLM result; queued for manual review
CREATE TABLE IF NOT EXISTS name_mappings (
    raw_name              TEXT PRIMARY KEY,
    cardmarket_product_id INTEGER REFERENCES cardmarket_products(id),
    llm_suggestion_id     INTEGER REFERENCES cardmarket_products(id),
    confidence            REAL,
    status                TEXT NOT NULL DEFAULT 'undecided'
                          CHECK(status IN ('mapped', 'null_mapped', 'undecided')),
    mapped_at             TEXT
);

CREATE TABLE IF NOT EXISTS price_readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES cardmarket_products(id),
    site_id    INTEGER NOT NULL REFERENCES sites(id),
    raw_name   TEXT NOT NULL,
    price      REAL NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'EUR',
    in_stock   INTEGER,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS thresholds (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES cardmarket_products(id),
    price      REAL NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
