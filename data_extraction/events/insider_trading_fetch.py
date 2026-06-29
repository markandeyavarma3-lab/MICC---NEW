"""
insider_trading_fetch.py – Fetch SEBI insider trading data using nsefin.
Run daily (incremental) or with --backfill for historical data.
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import logging

import time

import pandas as pd
import requests
import nsefin  # kept for import-compat; insider fetch now uses the NSE API directly

# --- SSL fix (removes broken env variable) ---
import os, certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\insider_trading.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("insider_trading")


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insider_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_date TEXT NOT NULL,
            symbol TEXT,
            company TEXT,
            name TEXT,
            category TEXT,
            transaction_type TEXT,
            quantity INTEGER,
            price REAL,
            value REAL,
            post_holding INTEGER,
            report_date TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_symbol ON insider_trading(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_filing_date ON insider_trading(filing_date)")
    conn.commit()
    log.info("Insider trading table ready.")


def safe_int(x):
    try:
        return int(float(x)) if x and x != '' else 0
    except:
        return 0

def safe_float(x):
    try:
        return float(x) if x and x != '' else 0.0
    except:
        return 0.0

def _pit_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
    })
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


def _fetch_pit(from_date_str, to_date_str):
    """Direct NSE corporates-pit fetch in monthly windows (nsefin returns nothing)."""
    s = _pit_session()
    start = pd.to_datetime(from_date_str).date()
    end = pd.to_datetime(to_date_str).date()
    all_rows, cur = [], start
    while cur <= end:
        nxt = min((pd.Timestamp(cur) + pd.offsets.MonthEnd(1)).date(), end)
        u = ("https://www.nseindia.com/api/corporates-pit?index=equities"
             f"&from_date={cur.strftime('%d-%m-%Y')}&to_date={nxt.strftime('%d-%m-%Y')}")
        try:
            data = s.get(u, timeout=30).json().get("data", [])
            all_rows.extend(data)
            log.info(f"  PIT {cur} .. {nxt}: {len(data)} records")
        except Exception as e:
            log.warning(f"  PIT {cur}..{nxt} error: {e}")
        time.sleep(0.7)
        cur = (pd.Timestamp(nxt) + pd.Timedelta(days=1)).date()
    return pd.DataFrame(all_rows)


def fetch_and_store(conn, from_date_str, to_date_str):
    """
    Fetch insider trades for a date range from the NSE corporates-pit API.
    Dates: 'yyyy-mm-dd' format.
    """
    try:
        log.info(f"Fetching insider trades from {from_date_str} to {to_date_str}")

        df = _fetch_pit(from_date_str, to_date_str)

        if df is None or df.empty:
            log.warning("No insider trading data returned.")
            return 0

        log.info(f"Fetched {len(df)} raw records.")

        # Convert date columns to datetime for filtering
        # The column 'intimDt' (intimation date) is in DD-MMM-YYYY format, e.g., '02-May-2026'
        # We'll convert both from_date and to_date to datetime for comparison
        df['intimDt_dt'] = pd.to_datetime(df['intimDt'], format='%d-%b-%Y', errors='coerce')
        from_dt = pd.to_datetime(from_date_str)
        to_dt = pd.to_datetime(to_date_str)
        mask = (df['intimDt_dt'] >= from_dt) & (df['intimDt_dt'] <= to_dt)
        df = df[mask].copy()

        if df.empty:
            log.warning(f"No data in date range {from_date_str} to {to_date_str}")
            return 0

        # Map columns to our schema
        # transaction_type: from 'tdpTransactionType' (e.g., 'Buy', 'Sell')
        # quantity: from 'secAcq' (securities acquired) or 'secDis'? Actually 'secAcq' is shares acquired,
        # but we also need 'sellquantity' if it's a sale. We'll unify: if transaction_type == 'Buy' use secAcq, else sellquantity.
        df['transaction_type'] = df['tdpTransactionType']
        df['quantity'] = 0
        buy_mask = df['transaction_type'] == 'Buy'
        sell_mask = df['transaction_type'] == 'Sell'
        df.loc[buy_mask, 'quantity'] = df.loc[buy_mask, 'secAcq'].apply(safe_int)
        df.loc[sell_mask, 'quantity'] = df.loc[sell_mask, 'sellquantity'].apply(safe_int)

        # Price: use buyValue / quantity or sellValue / quantity (if available)
        # But we have 'secVal' which is total value of transaction (in INR)
        df['value'] = df['secVal'].apply(safe_float)
        df['price'] = df.apply(lambda r: r['value'] / r['quantity'] if r['quantity'] > 0 else 0, axis=1)

        # Post holding: from 'afterAcqSharesNo' (after acquisition) – but this is only for the person,
        # can be used as post_holding.
        df['post_holding'] = df['afterAcqSharesNo'].apply(safe_int)

        # Fill missing numeric
        df['quantity'] = df['quantity'].fillna(0).astype(int)
        df['price'] = df['price'].fillna(0)
        df['value'] = df['value'].fillna(0)
        df['post_holding'] = df['post_holding'].fillna(0).astype(int)

        # Filing date: we use 'intimDt' as filing_date
        df['filing_date'] = pd.to_datetime(df['intimDt'], format='%d-%b-%Y').dt.strftime('%Y-%m-%d')
        df['report_date'] = df['filing_date']  # no separate report_date

        # Symbol, company, name, category
        df['symbol'] = df['symbol']
        df['company'] = df['company']
        df['name'] = df['acqName']
        df['category'] = df['personCategory']

        # Add last_updated
        df['last_updated'] = datetime.now().isoformat()

        # Select columns to insert
        columns = ['filing_date', 'symbol', 'company', 'name', 'category',
                   'transaction_type', 'quantity', 'price', 'value', 'post_holding',
                   'report_date', 'last_updated']
        df_out = df[columns]

        # Insert into database
        cursor = conn.cursor()
        inserted = 0
        for _, row in df_out.iterrows():
            # Check for duplicates (symbol, name, filing_date, quantity, price)
            cursor.execute("""
                SELECT 1 FROM insider_trading 
                WHERE filing_date = ? AND symbol = ? AND name = ? AND quantity = ? AND price = ?
            """, (row['filing_date'], row['symbol'], row['name'], row['quantity'], row['price']))
            if cursor.fetchone():
                continue

            cursor.execute("""
                INSERT INTO insider_trading
                (filing_date, symbol, company, name, category, transaction_type,
                 quantity, price, value, post_holding, report_date, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row['filing_date'], row['symbol'], row['company'], row['name'], row['category'],
                row['transaction_type'], row['quantity'], row['price'], row['value'],
                row['post_holding'], row['report_date'], row['last_updated']
            ))
            inserted += 1

        conn.commit()
        log.info(f"Inserted {inserted} new records from {len(df)} filtered records.")
        return inserted

    except Exception as e:
        log.error(f"Fetch/store error: {e}")
        import traceback
        log.error(traceback.format_exc())
        return 0


def incremental_update(conn):
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    log.info("--- INCREMENTAL UPDATE ---")
    fetch_and_store(conn, yesterday, today)


def historical_backfill(conn, from_date_str, to_date_str=None):
    if to_date_str is None:
        to_date_str = datetime.now().strftime('%Y-%m-%d')
    log.info(f"--- HISTORICAL BACKFILL from {from_date_str} to {to_date_str} ---")
    fetch_and_store(conn, from_date_str, to_date_str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="Historical backfill")
    parser.add_argument("--from-date", default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    create_table(conn)

    if args.backfill:
        historical_backfill(conn, args.from_date, args.to_date)
    else:
        incremental_update(conn)

    conn.close()
    log.info("Insider trading ETL finished.")