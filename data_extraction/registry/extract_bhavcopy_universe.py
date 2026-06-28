#!/usr/bin/env python3
"""Extract all traded EQ symbols from today's NSE bhavcopy CSV."""
import requests, csv, io, sqlite3, os, certifi
from datetime import datetime

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

URL = "https://archives.nseindia.com/content/equities/EQ_ISINCODE_CSV.zip"
DB = r"D:\marketDB\db\market.db"

resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
if resp.status_code != 200:
    print("Failed to download bhavcopy ZIP")
    exit()

import zipfile
with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
    csv_name = zf.namelist()[0]
    with zf.open(csv_name) as f:
        reader = csv.DictReader(io.TextIOWrapper(f))
        symbols = {row['SC_CODE']: row['SC_NAME'] for row in reader if row.get('SC_CODE')}

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS eq_bhavcopy_universe (symbol TEXT PRIMARY KEY, company_name TEXT, last_seen TEXT)""")
today = datetime.now().strftime("%Y-%m-%d")
for sym, name in symbols.items():
    conn.execute("INSERT OR REPLACE INTO eq_bhavcopy_universe VALUES (?,?,?)", (sym, name, today))
conn.commit()
conn.close()
print(f"Inserted {len(symbols)} symbols from today's bhavcopy.")