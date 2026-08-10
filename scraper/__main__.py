import logging
import sys

from scraper.runner import run_all_sites

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "pokemon.db"
    run_all_sites(db_path)
