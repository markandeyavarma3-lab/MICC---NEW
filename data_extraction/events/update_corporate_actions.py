#!/usr/bin/env python3
"""
update_corporate_actions.py – ONLY symbols present in stocks/all/ (parallel, progress).
"""
import sqlite3, time, logging, os, certifi
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
import yfinance as yf

DB_PATH = Path(r"D:\marketDB\db\market.db")
STOCKS_DIR = Path("stocks/all")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\corporate_actions.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)]
)
log = logging.getLogger("corp_actions")

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions (
            symbol TEXT, date TEXT, action_type TEXT,
            ratio REAL, amount REAL,
            PRIMARY KEY (symbol, date, action_type)
        )
    """)
    conn.commit()

def fetch_one(symbol):
    """Use symbol + .NS as Yahoo ticker."""
    yahoo = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yahoo)
        if ticker.history(period="5d").empty:
            return []
        splits = ticker.splits
        dividends = ticker.dividends
        rows = []
        for dt, ratio in splits.items():
            rows.append((symbol, dt.strftime("%Y-%m-%d"), "SPLIT", float(ratio), None))
        for dt, amount in dividends.items():
            rows.append((symbol, dt.strftime("%Y-%m-%d"), "DIVIDEND", None, float(amount)))
        return rows
    except:
        return []

def main():
    print("=" * 60)
    print("Corporate Actions – stocks with Parquet data only")

    if not STOCKS_DIR.exists():
        print("stocks/all/ directory not found.")
        return

    # Only directories that contain at least one .parquet file
    symbols = sorted([
        d.name for d in STOCKS_DIR.iterdir()
        if d.is_dir() and any(d.glob("*.parquet"))
    ])

    print(f"Found {len(symbols)} symbols with price data.")
    if not symbols:
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=60000")
    create_table(conn)

    total = len(symbols)
    print(f"Processing {total} symbols with 20 threads...")

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_one, sym): sym for sym in symbols}
        for future in tqdm(as_completed(futures), total=total, desc="Fetching", unit="sym"):
            sym = futures[future]
            try:
                data = future.result()
                if data:
                    conn.executemany("""
                        INSERT OR REPLACE INTO corporate_actions (symbol, date, action_type, ratio, amount)
                        VALUES (?, ?, ?, ?, ?)
                    """, data)
                    conn.commit()
            except Exception as e:
                log.error(f"{sym}: {e}")

    conn.close()
    print("✓ Corporate actions update complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()