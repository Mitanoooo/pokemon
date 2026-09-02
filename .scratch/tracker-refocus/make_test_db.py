"""Build a new-schema DB with server-sized data, for checking the ticket-20 pages.

Sites come from site_configs/ so the names and count match production; listings
and updates are synthetic but sized like the real thing (~2,900 listings, a
30-day updates window).
"""
import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pokemon-test.db")

SETS = ["Prismatic Evolutions", "Surging Sparks", "Stellar Crown", "Twilight Masquerade",
        "Paldean Fates", "Obsidian Flames", "151", "Journey Together", "Destined Rivals"]
KINDS = ["Elite Trainer Box", "Booster Bundle", "Booster Box", "Booster Pack",
         "Premium Collection", "Tin", "Blister", "Binder Collection", "ETB"]
STATES = ["in_stock"] * 6 + ["out_of_stock"] * 3 + ["preorder"] + ["unknown"]
MODES = ["presence", "text_map", "text_map,presence", "container_class_map", "attribute", None]
EVENTS = ["new_listing", "new_preorder", "back_in_stock", "price_drop", "price_rise"]

random.seed(20)

if TARGET.exists():
    TARGET.unlink()

conn = sqlite3.connect(TARGET)
conn.executescript((ROOT / "schema.sql").read_text())

configs = sorted((ROOT / "site_configs").glob("*.json"))
now = datetime.now(timezone.utc)
site_ids = []
for i, path in enumerate(configs):
    config = json.loads(path.read_text())
    url = config.get("source_url") or (config.get("source_urls") or [""])[0]
    name = config.get("name") or path.stem
    mode = MODES[i % len(MODES)]
    failures = 0 if i % 9 else random.randint(1, 4)
    cur = conn.execute(
        "INSERT INTO sites (url, name, last_scraped_at, last_error, consecutive_failures, "
        "null_price_count, availability_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url or f"https://{path.stem}", name,
         (now - timedelta(minutes=random.randint(0, 90))).strftime("%Y-%m-%d %H:%M:%S"),
         "HTTPSConnectionPool(host='x', port=443): Read timed out. (read timeout=20) "
         "after 3 attempts" if failures else None,
         failures, random.randint(0, 12), mode),
    )
    site_ids.append(cur.lastrowid)

run_id = conn.execute("INSERT INTO scrape_runs (started_at) VALUES (?)",
                      (now.strftime("%Y-%m-%d %H:%M:%S"),)).lastrowid

listings = []
for site_id in site_ids:
    for _ in range(random.randint(30, 130)):
        raw_name = f"Pokemon TCG {random.choice(SETS)} {random.choice(KINDS)}"
        if random.random() < 0.4:
            raw_name += f" ({random.randint(1, 400)})"
        price = round(random.uniform(4.9, 399.0), 2)
        first_seen = now - timedelta(days=random.randint(0, 400))
        listings.append((
            site_id, raw_name, f"https://shop.example/p/{abs(hash(raw_name)) % 10**7}",
            first_seen.strftime("%Y-%m-%d %H:%M:%S"),
            (now - timedelta(minutes=random.randint(0, 120))).strftime("%Y-%m-%d %H:%M:%S"),
            run_id, price, "EUR", random.choice(STATES), "Varastossa", 0,
        ))
conn.executemany(
    "INSERT OR IGNORE INTO listings (site_id, raw_name, product_url, first_seen_at, "
    "last_seen_at, last_run_id, latest_price, latest_currency, availability, "
    "availability_text, from_preorder_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    listings,
)

updates = []
for _ in range(3200):
    site_id, raw_name = random.choice(listings)[:2]
    event = random.choice(EVENTS)
    created = now - timedelta(minutes=random.randint(0, 30 * 24 * 60))
    old_price = round(random.uniform(4.9, 399.0), 2)
    if event in ("price_drop", "price_rise"):
        delta = random.uniform(0.01, 0.3) * old_price
        new_price = old_price - delta if event == "price_drop" else old_price + delta
        old_value, new_value = str(old_price), str(round(new_price, 2))
    elif event == "back_in_stock":
        old_value, new_value = random.choice(["out_of_stock", "preorder"]), "in_stock"
    else:
        old_value, new_value = None, str(old_price)
    updates.append((run_id, site_id, raw_name, event, old_value, new_value,
                    created.strftime("%Y-%m-%d %H:%M:%S"), random.randint(0, 1)))
conn.executemany(
    "INSERT INTO updates (run_id, site_id, raw_name, event_type, old_value, new_value, "
    "created_at, seen) VALUES (?,?,?,?,?,?,?,?)",
    updates,
)
conn.commit()

print(TARGET)
for table in ("sites", "listings", "updates"):
    print(table, conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
