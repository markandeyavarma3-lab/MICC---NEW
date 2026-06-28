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

BSE_EQ_URL = "https://www.bseindia.com/download/BhavCopy/Equity/EQ_ISINCODE_CSV.zip"

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
    """Download and parse the BSE equity ISIN file (CSV inside ZIP)."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(BSE_EQ_URL, headers=headers, timeout=30)
        if resp.status_code != 200:
            log.error(f"Failed to download BSE list. HTTP {resp.status_code}")
            return None
        # It's a ZIP containing a CSV
        import zipfile
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith('.csv')][0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f)
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