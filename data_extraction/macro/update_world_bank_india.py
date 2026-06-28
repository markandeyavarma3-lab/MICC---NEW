#!/usr/bin/env python3
"""
update_world_bank_india.py – World Bank India macro (SSL‑forced).
"""
import os, sys
# Delete the broken env variable BEFORE any request import
if 'REQUESTS_CA_BUNDLE' in os.environ:
    del os.environ['REQUESTS_CA_BUNDLE']
import certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import requests
import sqlite3
import logging
import time
from pathlib import Path
from datetime import datetime

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\world_bank.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger('wb_india')

INDICATORS = {
    'NY.GDP.MKTP.KD.ZG': 'GDP_growth_annual_pct',
    'NY.GDP.PCAP.KD.ZG': 'GDP_per_capita_growth_annual_pct',
    'FP.CPI.TOTL.ZG': 'Inflation_consumer_prices_annual_pct',
    'SL.UEM.TOTL.ZS': 'Unemployment_total_pct',
    'NE.EXP.GNFS.ZS': 'Exports_pct_GDP',
    'NE.IMP.GNFS.ZS': 'Imports_pct_GDP',
    'NE.TRD.GNFS.ZS': 'Trade_pct_GDP',
    'BN.CAB.XOKA.GD.ZS': 'Current_account_balance_pct_GDP',
    'BX.KLT.DINV.WD.GD.ZS': 'FDI_net_inflows_pct_GDP',
    'GC.DOD.TOTL.GD.ZS': 'Central_govt_debt_pct_GDP',
    'NY.GNS.ICTR.ZS': 'Gross_savings_pct_GDP',
    'NY.GDP.PCAP.CD': 'GDP_per_capita_USD',
    'SP.POP.TOTL': 'Population_total',
}

WB_API_URL = "http://api.worldbank.org/v2/country/IN/indicator/{indicator}?format=json&per_page=200"

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS world_bank_macro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            indicator_code TEXT NOT NULL,
            indicator_name TEXT NOT NULL,
            value REAL,
            last_updated TEXT,
            UNIQUE(date, indicator_code)
        )
    """)
    conn.commit()

def fetch_indicator_data(indicator_code):
    url = WB_API_URL.format(indicator=indicator_code)
    try:
        resp = requests.get(url, timeout=30, verify=True)
        resp.raise_for_status()
        data = resp.json()
        if not data or len(data) < 2:
            return []
        records = []
        for record in data[1]:
            year = record.get('date')
            value = record.get('value')
            if year and value not in (None, ''):
                records.append({'date': f"{year}-01-01", 'value': float(value)})
        return records
    except Exception as e:
        logger.error(f"Error fetching {indicator_code}: {e}")
        return []

def store_indicator_data(conn, indicator_code, indicator_name, records):
    if not records:
        return 0
    now = datetime.now().isoformat()
    inserted = 0
    for record in records:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO world_bank_macro
                (date, indicator_code, indicator_name, value, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (record['date'], indicator_code, indicator_name, record['value'], now))
            inserted += 1
        except sqlite3.Error as e:
            logger.error(f"DB error for {indicator_code}: {e}")
    conn.commit()
    return inserted

def main():
    logger.info("="*60)
    logger.info("World Bank India Macro Update")
    conn = sqlite3.connect(DB_PATH)
    create_table(conn)
    total = 0
    for code, name in INDICATORS.items():
        logger.info(f"Fetching {name} ({code})...")
        records = fetch_indicator_data(code)
        if records:
            inserted = store_indicator_data(conn, code, name, records)
            total += inserted
            logger.info(f"  [OK] Inserted {inserted} records")
        else:
            logger.warning(f"  [FAIL] No data for {name}")
        time.sleep(0.25)
    logger.info(f"Update complete. Total records inserted: {total}")
    conn.close()
    logger.info("="*60)

if __name__ == "__main__":
    main()