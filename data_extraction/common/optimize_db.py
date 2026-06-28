#!/usr/bin/env python3
"""
optimize_db.py – Run VACUUM and ANALYZE on market.db to reclaim space and update statistics.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\optimize_db.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("optimize")

def main():
    log.info("Starting database optimization...")
    conn = sqlite3.connect(DB_PATH)
    log.info("Running ANALYZE...")
    conn.execute("ANALYZE")
    log.info("Running VACUUM... (this may take several minutes)")
    conn.execute("VACUUM")
    log.info("Optimization complete.")
    conn.close()

if __name__ == "__main__":
    main()