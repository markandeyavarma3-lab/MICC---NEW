#!/usr/bin/env python3
"""
update_delivery.py – Fetches delivery percentage using nselib.
Handles missing values (' -') and auto converts to float.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from nselib import capital_market

# --- SSL fix (same as daily_update.py) ---
import os, certifi
if 'REQUESTS_CA_BUNDLE' in os.environ:
    if not os.path.isfile(os.environ['REQUESTS_CA_BUNDLE']):
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
else:
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\delivery.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger("delivery")

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_delivery (
            symbol TEXT, date TEXT, total_traded_qty REAL, delivery_qty REAL,
            delivery_percent REAL, PRIMARY KEY (symbol, date)
        )
    """)
    conn.commit()

def clean_numeric(series):
    """Convert a pandas series to float, replacing ' -' and other non-numeric with 0."""
    return pd.to_numeric(series.replace(' -', '0').replace('-', '0'), errors='coerce').fillna(0)

def get_trading_dates(lookback=7):
    dates = []
    d = datetime.today()
    while len(dates) < lookback:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return dates[::-1]

def fetch_delivery_for_date(date_str):
    try:
        trade_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
        log.info(f"Fetching delivery for {trade_date}...")
        df = capital_market.bhav_copy_with_delivery(trade_date=trade_date)
        if df.empty:
            log.warning(f"No data for {date_str}")
            return 0

        # Required columns (observed from test)
        required = ['SYMBOL', 'TTL_TRD_QNTY', 'DELIV_QTY']
        if not all(col in df.columns for col in required):
            log.warning(f"Missing columns. Available: {df.columns.tolist()}")
            return 0

        # If DELIV_PER exists, use it; else compute
        if 'DELIV_PER' in df.columns:
            delivery_pct = clean_numeric(df['DELIV_PER'])
        else:
            total = clean_numeric(df['TTL_TRD_QNTY'])
            delivery = clean_numeric(df['DELIV_QTY'])
            delivery_pct = (delivery / total) * 100
            delivery_pct = delivery_pct.replace([float('inf'), -float('inf')], 0).fillna(0)

        total_qty = clean_numeric(df['TTL_TRD_QNTY'])
        delivery_qty = clean_numeric(df['DELIV_QTY'])
        symbols = df['SYMBOL'].astype(str).str.strip()

        # Build rows
        rows = []
        for sym, tq, dq, dp in zip(symbols, total_qty, delivery_qty, delivery_pct):
            if tq > 0:  # only if traded
                rows.append((sym, date_str, float(tq), float(dq), float(dp)))

        if not rows:
            log.info(f"No valid rows for {date_str}")
            return 0

        conn = sqlite3.connect(DB_PATH)
        conn.executemany("""
            INSERT OR REPLACE INTO stock_delivery (symbol, date, total_traded_qty, delivery_qty, delivery_percent)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()
        log.info(f"Inserted {len(rows)} rows for {date_str}")
        return len(rows)
    except Exception as e:
        log.error(f"Failed {date_str}: {e}")
        return 0

def main():
    log.info("="*55)
    log.info("Starting Delivery % update (with data cleaning)")
    conn = sqlite3.connect(DB_PATH)
    create_table(conn)
    conn.close()

    dates = get_trading_dates(7)
    total = 0
    for d in dates:
        total += fetch_delivery_for_date(d)
    log.info(f"Delivery update complete. Total rows added: {total}")
    log.info("="*55)

if __name__ == "__main__":
    main()


def update_delivery():
    return None