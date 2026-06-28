#!/usr/bin/env python3
"""Extract all listed NSE EQ symbols into eq_bhavcopy_universe.

Source: NSE EQUITY_L master (same reliable endpoint used by build_tradable_universe).
The previous URL (EQ_ISINCODE_CSV.zip) was dead and used BSE columns.
"""
import requests, csv, io, sqlite3, os, certifi
from datetime import datetime

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
DB = r"D:\marketDB\db\market.db"

resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
if resp.status_code != 200:
    print(f"Failed to download EQUITY_L.csv (HTTP {resp.status_code})")
    exit()

reader = csv.DictReader(io.StringIO(resp.text))
symbols = {
    row['SYMBOL'].strip(): row.get('NAME OF COMPANY', '').strip()
    for row in reader if row.get('SYMBOL', '').strip()
}

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS eq_bhavcopy_universe (
    symbol TEXT PRIMARY KEY, company_name TEXT, last_seen TEXT)""")
today = datetime.now().strftime("%Y-%m-%d")
for sym, name in symbols.items():
    conn.execute("INSERT OR REPLACE INTO eq_bhavcopy_universe VALUES (?,?,?)", (sym, name, today))
conn.commit()
conn.close()
print(f"Inserted {len(symbols)} EQ symbols from NSE EQUITY_L.")
