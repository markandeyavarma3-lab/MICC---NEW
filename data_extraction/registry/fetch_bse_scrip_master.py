#!/usr/bin/env python3
"""fetch_bse_scrip_master.py — Part 4 Stage 3: FULL BSE scrip identity master.

The Stage-2 survivorship finding: SHP enumeration used ListofScripData?status=Active
only, so delisted names were invisible. Stage-3 probe (2026-07-05) confirmed the same
endpoint serves status=Delisted (4,612 scrips) and status=Suspended (1,226) — with
ISINs — and that SHPQNewFormat serves a delisted scrip's full filing history (verified
on DHFL/511072 up to its Jun-2021 delisting).

This builds `bse_scrip_master`: one row per scrip across Active+Delisted+Suspended,
the authoritative ISIN->scrip map INCLUDING dead names. Additive, idempotent
(INSERT OR REPLACE keyed on scrip). ~3 API calls total — safe to run any time.

Run:  py -3.14 registry/fetch_bse_scrip_master.py
"""
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import certifi
import os
import requests

os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
DB_PATH = Path(r"D:\marketDB\db\market.db")
API = "https://api.bseindia.com/BseIndiaAPI/api"
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}
SME_GROUPS = {"M", "MT", "MS"}
STATUSES = ("Active", "Delisted", "Suspended")

DDL = """CREATE TABLE IF NOT EXISTS bse_scrip_master (
    scrip_code     TEXT PRIMARY KEY,
    isin           TEXT,
    company_name   TEXT,
    listing_status TEXT,   -- Active | Delisted | Suspended (as of fetched_at)
    grp            TEXT,   -- BSE group (M/MT/MS => SME)
    segment_guess  TEXT,   -- 'sme' | 'mainboard'
    fetched_at     TEXT
)"""


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute(DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bsm_isin ON bse_scrip_master(isin)")

    s = requests.Session()
    s.headers.update(HDRS)
    s.get("https://www.bseindia.com/", timeout=20)
    now = datetime.now().isoformat(timespec="seconds")

    total = 0
    for status in STATUSES:
        time.sleep(1.0)
        r = s.get(f"{API}/ListofScripData/w?Group=&Scripcode=&industry="
                  f"&segment=Equity&status={status}", timeout=90)
        rows = r.json() if "json" in r.headers.get("content-type", "") else []
        n = 0
        for x in rows:
            scrip = str(x.get("SCRIP_CD", "")).strip()
            if not scrip:
                continue
            grp = str(x.get("GROUP", "") or "").strip()
            conn.execute(
                "INSERT OR REPLACE INTO bse_scrip_master VALUES (?,?,?,?,?,?,?)",
                (scrip, (x.get("ISIN_NUMBER") or "").strip(),
                 (x.get("Issuer_Name") or x.get("Scrip_Name") or "").strip(),
                 status, grp, "sme" if grp in SME_GROUPS else "mainboard", now))
            n += 1
        conn.commit()
        total += n
        print(f"  {status}: {n} scrips", flush=True)

    counts = conn.execute("SELECT listing_status, COUNT(*) FROM bse_scrip_master "
                          "GROUP BY listing_status").fetchall()
    print(f"bse_scrip_master: {total} upserted this run | table now: {counts}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
