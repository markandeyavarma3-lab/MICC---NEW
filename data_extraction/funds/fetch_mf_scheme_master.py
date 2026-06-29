#!/usr/bin/env python3
"""fetch_mf_scheme_master.py — MF scheme master (code, name, ISIN, AMC, category,
scheme type) parsed from AMFI NAVAll.txt. Links the mf_nav_history scheme codes to
their AMC + category. Idempotent.

Run:  py -3.14 funds/fetch_mf_scheme_master.py
"""
import sqlite3, re
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    txt = s.get("https://www.amfiindia.com/spages/NAVAll.txt", timeout=60).text

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS mf_scheme_master (
        scheme_code TEXT PRIMARY KEY, scheme_name TEXT, isin TEXT,
        amc TEXT, category TEXT, scheme_type TEXT, updated TEXT)""")
    conn.commit()

    now = datetime.now().isoformat()
    category = scheme_type = amc = ""
    rows = []
    for line in txt.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        if "Schemes(" in line or "Scheme(" in line:        # section header => type/category
            scheme_type = line.strip()
            m = re.search(r"\((.*?)\)", line)
            category = m.group(1).strip() if m else line.strip()
            continue
        if line.count(";") >= 5:                            # scheme data row
            p = line.split(";")
            if not p[0].strip().isdigit():                  # skip the column header row
                continue
            isin = p[1].strip() if p[1].strip() not in ("", "-") else (
                p[2].strip() if p[2].strip() not in ("", "-") else None)
            rows.append((p[0].strip(), p[3].strip(), isin, amc, category, scheme_type, now))
        else:                                               # AMC name line
            amc = line.strip()

    if rows:
        conn.executemany("INSERT OR REPLACE INTO mf_scheme_master VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT amc),COUNT(DISTINCT category) FROM mf_scheme_master").fetchone()
    conn.close()
    print(f"DONE: mf_scheme_master {n[0]:,} schemes, {n[1]} AMCs, {n[2]} categories", flush=True)


if __name__ == "__main__":
    main()
