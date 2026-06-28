#!/usr/bin/env python3
"""
update_macro_india_fred.py – Fetch India‑specific macro series from FRED.
Uses the same API key as update_macro_us.py.
"""
import sqlite3, time, logging, os, certifi
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from fredapi import Fred
from tenacity import retry, stop_after_attempt, wait_exponential

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\india_macro_fred.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("india_macro_fred")

FRED_API_KEY = os.getenv("FRED_API_KEY", "")  # set FRED_API_KEY in your environment

# Series metadata: (fred_id, display_name, frequency)
INDIA_SERIES = {
    "INDCPIALLQINMEI":   ("India CPI (OECD)", "quarterly"),
    # "INDGDPRQDSMEI":    ("India Real GDP Growth", "quarterly"),          # → now from World Bank
    # "LRUN64TTINQ156S":  ("India Unemployment Rate", "quarterly"),        # → now from World Bank
    # "IRLTLT01INM156N":  ("India 10Y Bond Yield", "monthly"),            # → add later from RBI if needed
    "TRESEGINM194N":    ("India Forex Reserves (USD)", "monthly"),
    "XTEXVA01INM664S":  ("India Exports (USD)", "monthly"),
    "XTIMVA01INM664S":  ("India Imports (USD)", "monthly"),
}

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS india_macro_fred (
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL,
            frequency TEXT,
            last_updated TEXT,
            PRIMARY KEY (series_id, date)
        )
    """)
    conn.commit()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def fetch_series(fred, fred_id, start_date, end_date):
    return fred.get_series(fred_id, observation_start=start_date, observation_end=end_date)

def store_series(conn, series_id, display_name, frequency, data):
    now = datetime.now().isoformat()
    inserted = 0
    for dt, val in data.items():
        if pd.isna(val):
            continue
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10]
        try:
            conn.execute("""
                INSERT OR REPLACE INTO india_macro_fred
                (series_id, date, value, frequency, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (series_id, date_str, float(val), frequency, now))
            inserted += 1
        except Exception as e:
            log.error(f"Store error {series_id} {date_str}: {e}")
    conn.commit()
    return inserted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--daily", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("India Macro from FRED")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=60000")
    create_table(conn)

    fred = Fred(api_key=FRED_API_KEY)

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = "2010-01-01" if args.backfill else \
                 (datetime.strptime(yesterday, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")

    total = 0
    for fred_id, (display_name, freq) in INDIA_SERIES.items():
        log.info(f"Fetching {display_name} ({fred_id}) from {start_date} to {yesterday}")
        try:
            data = fetch_series(fred, fred_id, start_date, yesterday)
            if data is not None and not data.empty:
                inserted = store_series(conn, fred_id, display_name, freq, data)
                log.info(f"  -> {inserted} rows inserted")
                total += inserted
            else:
                log.info(f"  -> No new data")
        except Exception as e:
            log.error(f"Failed {display_name}: {e}")
        time.sleep(1.0)

    conn.close()
    log.info(f"India macro update complete. Total rows: {total}")
    log.info("=" * 60)

if __name__ == "__main__":
    import argparse
    main()