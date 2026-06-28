#!/usr/bin/env python3
"""
refresh_bse_registry.py – Download BSE equity list and store in market.db
"""
import sqlite3, requests, io, os, certifi, logging, time
from pathlib import Path
from datetime import datetime
import pandas as pd

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\bse_registry.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("bse_registry")

BSE_API_URL = ("https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
               "?Group=&Scripcode=&industry=&segment=Equity&status=Active")

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bse_stock_registry (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            isin TEXT,
            sector TEXT,
            face_value REAL,
            yahoo_symbol TEXT,
            is_active INTEGER DEFAULT 1,
            last_updated TEXT
        )
    """)
    conn.commit()

def download_bse_list():
    """Fetch the active BSE equity list from the BSE JSON API.
    (The old EQ_ISINCODE_CSV.zip endpoint is dead / anti-bot protected.)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/",
        "Origin": "https://www.bseindia.com",
    }
    try:
        s = requests.Session()
        s.headers.update(headers)
        s.get("https://www.bseindia.com/", timeout=15)  # prime cookies
        resp = s.get(BSE_API_URL, timeout=30)
        if resp.status_code != 200:
            log.error(f"Failed to download BSE list. HTTP {resp.status_code}")
            return None
        df = pd.DataFrame(resp.json())
        if df.empty:
            log.error("BSE API returned no records.")
            return None
        # Normalize to the columns update_registry expects
        df = df.rename(columns={
            "SCRIP_CD": "SC_CODE", "Scrip_Name": "SC_NAME", "ISIN_NUMBER": "ISIN_CODE",
        })
        return df
    except Exception as e:
        log.error(f"Error downloading BSE list: {e}")
        return None

def update_registry(conn, df):
    """Insert/update BSE symbols."""
    now = datetime.now().isoformat()
    count = 0
    for _, row in df.iterrows():
        try:
            symbol = str(row.get('SC_CODE','')).strip()
            name = str(row.get('SC_NAME','')).strip()
            isin = str(row.get('ISIN_CODE','')).strip()
            if not symbol:
                continue
            yahoo_symbol = f"{symbol}.BO"
            conn.execute("""
                INSERT OR REPLACE INTO bse_stock_registry
                (symbol, company_name, isin, yahoo_symbol, is_active, last_updated)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (symbol, name, isin, yahoo_symbol, now))
            count += 1
        except:
            pass
    conn.commit()
    log.info(f"Inserted/updated {count} BSE symbols")

def main():
    log.info("=" * 60)
    log.info("BSE Stock Registry Refresh")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=60000")
    create_table(conn)

    df = download_bse_list()
    if df is not None:
        update_registry(conn, df)
    else:
        log.error("Could not update BSE registry.")

    conn.close()
    log.info("Done")
    log.info("=" * 60)

if __name__ == "__main__":
    main()