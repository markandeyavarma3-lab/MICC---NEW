"""
refresh_stock_registry.py – Updates stock_registry table.
Handles missing columns gracefully.
"""

import sqlite3
import pandas as pd
import requests
import io
import time
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
NSE_EQUITY_URL = "https://www.nseindia.com/api/equity-stock?csv=true"
FALLBACK_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


def make_nse_session():
    """Create a requests.Session with NSE cookies using Selenium."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.nseindia.com")
    time.sleep(3)

    cookies = driver.get_cookies()
    driver.quit()

    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.nseindia.com/",
    })
    return session


def download_equity_list():
    """Try NSE API first, fallback to static CSV."""
    session = make_nse_session()
    try:
        resp = session.get(NSE_EQUITY_URL, timeout=30)
        if resp.status_code == 200 and "SYMBOL" in resp.text:
            df = pd.read_csv(io.StringIO(resp.text))
            return df
    except Exception as e:
        print(f"API failed: {e}, trying fallback...")

    try:
        df = pd.read_csv(FALLBACK_URL)
        return df
    except Exception as e:
        print(f"Fallback also failed: {e}")
        return None


def ensure_columns(cursor):
    """Add missing columns to stock_registry if needed."""
    # Get existing columns
    cursor.execute("PRAGMA table_info(stock_registry)")
    columns = [row[1] for row in cursor.fetchall()]

    if "last_updated" not in columns:
        print("Adding column 'last_updated' to stock_registry...")
        cursor.execute("ALTER TABLE stock_registry ADD COLUMN last_updated TEXT")

    if "yahoo_symbol" not in columns:
        print("Adding column 'yahoo_symbol' to stock_registry...")
        cursor.execute("ALTER TABLE stock_registry ADD COLUMN yahoo_symbol TEXT")

    if "is_active" not in columns:
        print("Adding column 'is_active' to stock_registry...")
        cursor.execute("ALTER TABLE stock_registry ADD COLUMN is_active INTEGER DEFAULT 1")


def update_registry(df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create table if not exists (with all columns)
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS stock_registry
                   (
                       symbol
                       TEXT
                       PRIMARY
                       KEY,
                       company_name
                       TEXT,
                       is_active
                       INTEGER
                       DEFAULT
                       1,
                       yahoo_symbol
                       TEXT,
                       last_updated
                       TEXT
                   )
                   """)

    # Ensure any missing columns in existing table
    ensure_columns(cursor)

    # Get existing symbols
    existing = {row[0] for row in cursor.execute("SELECT symbol FROM stock_registry").fetchall()}
    inserted = 0
    today = datetime.today().strftime("%Y-%m-%d")

    for _, row in df.iterrows():
        symbol = str(row.get("SYMBOL", "")).strip()
        name = str(row.get("NAME OF COMPANY", "")).strip()
        if not symbol:
            continue
        yahoo_symbol = f"{symbol}.NS"

        if symbol not in existing:
            cursor.execute("""
                           INSERT INTO stock_registry (symbol, company_name, is_active, yahoo_symbol, last_updated)
                           VALUES (?, ?, 1, ?, ?)
                           """, (symbol, name, yahoo_symbol, today))
            inserted += 1
        else:
            cursor.execute("""
                           UPDATE stock_registry
                           SET last_updated = ?,
                               is_active    = 1
                           WHERE symbol = ?
                           """, (today, symbol))

    # Mark missing symbols as inactive
    new_symbols = {str(row.get("SYMBOL", "")).strip() for _, row in df.iterrows()}
    for old_sym in existing:
        if old_sym not in new_symbols:
            cursor.execute("UPDATE stock_registry SET is_active = 0 WHERE symbol = ?", (old_sym,))

    conn.commit()
    conn.close()
    print(f"Registry updated: {inserted} new symbols added. Total active: {len(new_symbols)}")


def main():
    print("Downloading NSE equity list...")
    df = download_equity_list()
    if df is not None:
        update_registry(df)
        print("Stock registry refreshed.")
    else:
        print("Failed to update registry.")


if __name__ == "__main__":
    main()