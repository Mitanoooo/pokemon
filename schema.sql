CREATE TABLE IF NOT EXISTS sites (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    url                  TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    last_scraped_at      TEXT,
    last_error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    null_price_count     INTEGER NOT NULL DEFAULT 0,
    -- Availability resolution forms configured for this site, comma-joined in
    -- precedence order (e.g. "text_map,container_class"). Written on every run
    -- from the site config, so the app never reads config files.
    -- NULL means the config has no availability block: the site is untracked.
    availability_mode    TEXT
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

-- One row per (shop, raw listing name). availability is overwritten on every
-- sighting: it means "state as of the last time we saw this listing", not
-- "best state ever known". latest_price keeps its COALESCE behaviour, so a
-- sighting with no parseable price does not erase the last known price.
CREATE TABLE IF NOT EXISTS listings (
    site_id           INTEGER NOT NULL REFERENCES sites(id),
    raw_name          TEXT NOT NULL,
    product_url       TEXT,
    first_seen_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_run_id       INTEGER REFERENCES scrape_runs(id),
    latest_price      REAL,
    latest_currency   TEXT,
    availability      TEXT NOT NULL DEFAULT 'unknown'
                      CHECK (availability IN ('in_stock', 'out_of_stock', 'preorder', 'unknown')),
    -- Raw badge text or class list that produced availability, capped 120 chars,
    -- so a misread can be re-derived without re-scraping.
    availability_text TEXT,
    from_preorder_url INTEGER NOT NULL DEFAULT 0 CHECK (from_preorder_url IN (0, 1)),
    PRIMARY KEY (site_id, raw_name)
);

CREATE TABLE IF NOT EXISTS updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER REFERENCES scrape_runs(id),
    site_id    INTEGER NOT NULL REFERENCES sites(id),
    raw_name   TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN
                   ('new_listing', 'new_preorder', 'back_in_stock', 'price_drop', 'price_rise')),
    old_value  TEXT,
    new_value  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    seen       INTEGER NOT NULL DEFAULT 0
);

-- Keywords the operator is following right now, e.g. 'ascended'. The Updates
-- page highlights matching rows. They live here rather than in session state so
-- they survive a browser reload, an app restart and a different device: a set
-- someone typed once is meant to stay until they clear it.
CREATE TABLE IF NOT EXISTS watch_keywords (
    keyword    TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sites the operator wants alerted on regardless of keyword matching.
CREATE TABLE IF NOT EXISTS watch_sites (
    site_id    INTEGER PRIMARY KEY REFERENCES sites(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_listings_raw_name ON listings(raw_name);
CREATE INDEX IF NOT EXISTS idx_listings_site_availability ON listings(site_id, availability);
CREATE INDEX IF NOT EXISTS idx_updates_created_at ON updates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_updates_type_created_at ON updates(event_type, created_at DESC);
