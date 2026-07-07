#!/usr/bin/env python3
"""
update_macro_us.py – Institutional‑grade US macroeconomic data from FRED.
Supports full historical backfill and incremental daily updates.
Fixed to use correct FRED series IDs.
"""

import os
import sqlite3
import logging
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fredapi import Fred
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ---------- CONFIGURATION ----------
DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\macro_us.log")
LOG_FILE.parent.mkdir(exist_ok=True)

# FRED API key — set FRED_API_KEY in your environment (see README / .env.example)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Series metadata: (fred_id, display_name, frequency, start_date)
SERIES_METADATA = {
    "GDP":                ("GDP",                 "Gross Domestic Product", "quarterly", "1947-01-01"),
    "GDP_Growth":         ("A191RL1Q225SBEA",     "Real GDP Growth Rate",   "quarterly", "1947-01-01"),
    "Inflation_CPI":      ("CPIAUCSL",            "Consumer Price Index (All Urban)", "monthly", "1947-01-01"),
    "Inflation_Core":     ("CPILFESL",            "Core CPI (ex food & energy)", "monthly", "1957-01-01"),
    "Unemployment":       ("UNRATE",              "Unemployment Rate",      "monthly", "1948-01-01"),
    "Fed_Funds":          ("FEDFUNDS",            "Effective Federal Funds Rate", "monthly", "1954-07-01"),
    "10Y_Treasury":       ("DGS10",               "10-Year Treasury Yield", "daily", "1962-01-02"),
    "2Y_Treasury":        ("DGS2",                "2-Year Treasury Yield",  "daily", "1976-06-01"),
    "VIX":                ("VIXCLS",              "CBOE Volatility Index",  "daily", "1990-01-02"),
    "Consumer_Confidence":("UMCSENT",             "Consumer Sentiment",     "monthly", "1978-01-01"),
    "Industrial_Production":("INDPRO",            "Industrial Production",  "monthly", "1919-01-01"),
}

# Additional computed series (not fetched directly)
COMPUTED_SERIES = ["Term_Spread"]

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("macro_us")

# ---------- DATABASE SETUP ----------
def create_tables(conn):
    """Create us_macro_data table with indexes."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS us_macro_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL,
            frequency TEXT,
            last_updated TEXT,
            UNIQUE(series_id, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_date ON us_macro_data(series_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON us_macro_data(date)")
    conn.commit()
    log.info("US macro table ready")

def get_last_date(conn, series_id: str) -> Optional[str]:
    """Return the most recent date stored for a series (YYYY-MM-DD)."""
    row = conn.execute(
        "SELECT MAX(date) FROM us_macro_data WHERE series_id = ?", (series_id,)
    ).fetchone()
    return row[0] if row and row[0] else None

def store_series(conn, series_id: str, df: pd.DataFrame, frequency: str):
    """Store dataframe with columns 'date' and 'value' into us_macro_data."""
    now = datetime.now().isoformat()
    inserted = 0
    for _, row in df.iterrows():
        date_str = row['date'].strftime("%Y-%m-%d")
        value = float(row['value']) if pd.notna(row['value']) else None
        try:
            conn.execute("""
                INSERT OR REPLACE INTO us_macro_data (series_id, date, value, frequency, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (series_id, date_str, value, frequency, now))
            inserted += 1
        except Exception as e:
            log.error(f"Store error {series_id} {date_str}: {e}")
    conn.commit()
    return inserted

# ---------- FRED FETCH WITH RETRY ----------
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def fetch_fred_series(fred: Fred, fred_id: str, start_date: str, end_date: str) -> pd.Series:
    """Fetch series using the actual FRED series ID."""
    return fred.get_series(fred_id, observation_start=start_date, observation_end=end_date)

def fetch_term_spread(fred: Fred, start_date: str, end_date: str) -> pd.DataFrame:
    """Compute term spread = 10Y - 2Y."""
    dgs10 = fetch_fred_series(fred, "DGS10", start_date, end_date)
    dgs2 = fetch_fred_series(fred, "DGS2", start_date, end_date)
    common = dgs10.index.intersection(dgs2.index)
    spread = (dgs10[common] - dgs2[common]).dropna()
    df = pd.DataFrame({'date': spread.index, 'value': spread.values})
    return df

# ---------- BACKFILL / INCREMENTAL UPDATE ----------
def update_series(conn, fred: Fred, series_key: str, fred_id: str, display_name: str, frequency: str, start_date: str, full_backfill: bool = False):
    """Fetch data from last stored date (or start_date if backfill) to yesterday."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last = get_last_date(conn, series_key)
    if full_backfill or last is None:
        fetch_start = start_date
        log.info(f"Backfilling {display_name} from {fetch_start} to {yesterday}")
    else:
        fetch_start = (datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if fetch_start > yesterday:
            log.info(f"{display_name} already up to date (last={last})")
            return 0
        log.info(f"Incremental update for {display_name} from {fetch_start} to {yesterday}")

    try:
        data = fetch_fred_series(fred, fred_id, fetch_start, yesterday)
        if data is None or data.empty:
            log.info(f"No new data for {display_name}")
            return 0
        df = pd.DataFrame({'date': data.index, 'value': data.values})
        inserted = store_series(conn, series_key, df, frequency)
        log.info(f"Inserted {inserted} rows for {display_name}")
        return inserted
    except Exception as e:
        log.error(f"Failed to update {display_name}: {e}")
        return 0

def update_computed_term_spread(conn, fred: Fred, full_backfill: bool = False):
    """Update term spread (computed series)."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last = get_last_date(conn, "Term_Spread")
    if full_backfill or last is None:
        fetch_start = "1976-06-01"  # when 2Y data starts
        log.info(f"Backfilling Term Spread from {fetch_start} to {yesterday}")
    else:
        fetch_start = (datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if fetch_start > yesterday:
            log.info("Term Spread already up to date")
            return 0
        log.info(f"Incremental update for Term Spread from {fetch_start} to {yesterday}")
    try:
        df = fetch_term_spread(fred, fetch_start, yesterday)
        if df.empty:
            log.info("No new term spread data")
            return 0
        inserted = store_series(conn, "Term_Spread", df, "daily")
        log.info(f"Inserted {inserted} rows for Term Spread")
        return inserted
    except Exception as e:
        log.error(f"Failed to update Term Spread: {e}")
        return 0

# ---------- MAIN ----------
def main():
    parser = argparse.ArgumentParser(description="FRED US Macro Data Updater")
    parser.add_argument("--backfill", action="store_true", help="Perform full historical backfill (one-time)")
    parser.add_argument("--daily", action="store_true", help="Run incremental daily update (default)")
    args = parser.parse_args()

    full_backfill = args.backfill
    if not full_backfill and not args.daily:
        full_backfill = False

    log.info("=" * 70)
    log.info(f"US Macro Update – {'FULL BACKFILL' if full_backfill else 'INCREMENTAL UPDATE'}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 60000")
    create_tables(conn)

    try:
        fred = Fred(api_key=FRED_API_KEY)
    except Exception as e:
        log.error(f"Failed to initialize FRED: {e}")
        return

    total = 0
    for series_key, (fred_id, display_name, freq, start) in SERIES_METADATA.items():
        inserted = update_series(conn, fred, series_key, fred_id, display_name, freq, start, full_backfill)
        total += inserted
        time.sleep(1.0)

    total += update_computed_term_spread(conn, fred, full_backfill)

    conn.execute("PRAGMA optimize")
    conn.close()
    log.info(f"Update complete. Total new rows inserted: {total}")
    log.info("=" * 70)

if __name__ == "__main__":
    main()