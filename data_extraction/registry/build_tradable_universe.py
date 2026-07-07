#!/usr/bin/env python3
"""Build the clean tradable EQ universe directly from NSE (no filters needed)."""
import sqlite3, os, certifi, csv, io
from datetime import datetime
import requests

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
DB = r"D:\MICC\marketDB\db\market.db"

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(URL, headers=headers, timeout=15)
if resp.status_code != 200:
    print("Failed to download EQUITY_L.csv")
    exit()

reader = csv.DictReader(io.StringIO(resp.text))
stocks = {}
for row in reader:
    sym = row.get('SYMBOL', '').strip()
    name = row.get('NAME OF COMPANY', '').strip()
    if sym:
        stocks[sym] = name

conn = sqlite3.connect(DB)
conn.execute("""
    CREATE TABLE IF NOT EXISTS tradable_eq_stocks (
        symbol TEXT PRIMARY KEY,
        company_name TEXT,
        updated TEXT
    )
""")
today = datetime.now().strftime("%Y-%m-%d")
for sym, name in stocks.items():
    conn.execute("INSERT OR REPLACE INTO tradable_eq_stocks VALUES (?,?,?)",
                 (sym, name, today))
conn.commit()
conn.close()
print(f"Clean tradable EQ universe: {len(stocks)} stocks")