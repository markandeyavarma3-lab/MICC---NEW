#!/usr/bin/env python3
"""
phase4_corporate_announcements.py – Fetch corporate announcements from NSE.
Run daily after market close.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import nsefin
# --- SSL fix ---
import os, certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\corporate_announcements.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("corp_ann")

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_date TEXT NOT NULL,
            symbol TEXT,
            subject TEXT,
            attachment_url TEXT,
            received_date TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_corp_symbol ON corporate_announcements(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_corp_date ON corporate_announcements(announcement_date)")
    conn.commit()
    log.info("Corporate announcements table ready")

def parse_nse_date(dt_str):
    """Convert NSE date string (DDMMYYYYHHMMSS) to YYYY-MM-DD."""
    try:
        return datetime.strptime(dt_str[:8], "%d%m%Y").strftime("%Y-%m-%d")
    except:
        return None

def fetch_announcements():
    """Fetch corporate announcements (returns DataFrame)."""
    client = nsefin.NSEClient()
    try:
        df = client.get_corporate_announcements()
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        log.error(f"Error fetching announcements: {e}")
        return None

def store_announcements(conn, df):
    if df is None or df.empty:
        return 0

    # Rename columns to expected names
    # Observed columns: symbol, desc, dt (date in DDMMYYYYHHMMSS), url?, etc.
    # Map 'desc' -> subject
    df.rename(columns={'desc': 'subject'}, inplace=True)

    # Extract announcement_date from 'dt' (if exists)
    if 'dt' in df.columns:
        df['announcement_date'] = df['dt'].apply(parse_nse_date)
    else:
        log.error("Missing 'dt' column")
        return 0

    # Use current date as fallback for missing
    df['announcement_date'] = df['announcement_date'].fillna(datetime.now().strftime("%Y-%m-%d"))

    # Ensure required columns
    if 'symbol' not in df.columns:
        log.error("Missing 'symbol' column")
        return 0
    if 'subject' not in df.columns:
        df['subject'] = None
    if 'attachment_url' not in df.columns:
        # Try to find a column that looks like a URL, else None
        url_col = next((c for c in df.columns if 'url' in c.lower()), None)
        if url_col:
            df.rename(columns={url_col: 'attachment_url'}, inplace=True)
        else:
            df['attachment_url'] = None

    # received_date not present, use announcement_date
    df['received_date'] = df['announcement_date']
    df['last_updated'] = datetime.now().isoformat()

    # Insert
    cursor = conn.cursor()
    inserted = 0
    for _, row in df.iterrows():
        # Duplicate check on date, symbol, subject
        cursor.execute("""
            SELECT 1 FROM corporate_announcements
            WHERE announcement_date=? AND symbol=? AND subject=?
        """, (row['announcement_date'], row['symbol'], row['subject']))
        if cursor.fetchone():
            continue
        cursor.execute("""
            INSERT INTO corporate_announcements
            (announcement_date, symbol, subject, attachment_url, received_date, last_updated)
            VALUES (?,?,?,?,?,?)
        """, (row['announcement_date'], row['symbol'], row['subject'], row.get('attachment_url'), row['received_date'], row['last_updated']))
        inserted += 1
    conn.commit()
    log.info(f"Inserted {inserted} corporate announcements")
    return inserted

def daily_update(conn):
    log.info("Fetching recent corporate announcements...")
    df = fetch_announcements()
    if df is not None:
        store_announcements(conn, df)
    else:
        log.warning("No announcements fetched")

def backfill(conn):
    log.info("Backfilling corporate announcements (same as daily update, but we can fetch more by pagination if needed).")
    daily_update(conn)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="Backfill historical announcements")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    if args.backfill:
        backfill(conn)
    else:
        daily_update(conn)

    conn.close()
    log.info("Done.")