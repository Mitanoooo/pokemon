import logging
import os
import sys

from dotenv import load_dotenv

from scraper.runner import run_all_sites

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "pokemon.db"
    run_all_sites(db_path, discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", ""))
