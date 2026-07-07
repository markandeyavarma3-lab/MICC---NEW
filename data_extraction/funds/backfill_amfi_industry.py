#!/usr/bin/env python3
"""backfill_amfi_industry.py — Monthly MF industry data by scheme category
(schemes, folios, funds mobilized, net inflow/outflow, AUM, avg AUM) from AMFI
monthly reports: portal.amfiindia.com/spages/am{mmm}{yyyy}repo.xls (.xls ~2019+).
The domestic-flow counterweight to FII/DII. Idempotent.

Run:  py -3.14 funds/backfill_amfi_industry.py
"""
import sqlite3, io, time
from pathlib import Path
from datetime import date

import requests
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS mf_industry_monthly (
        report_month TEXT, category TEXT, num_schemes REAL, num_folios REAL,
        funds_mobilized REAL, redemption REAL, net_flow REAL, aum REAL, avg_aum REAL,
        PRIMARY KEY(report_month, category))""")
    conn.commit()


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def parse_report(content, ym):
    try:
        # Sheet name varies by month (MCR_MonthlyReport / MCR_Report / "Jun 2021" / ...),
        # but it's always the first sheet with the same first 9 columns.
        df = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None)
    except Exception:
        return []
    rows = []
    for _, r in df.iterrows():
        if len(r) < 9:
            continue
        name = str(r[1]).strip() if pd.notna(r[1]) else ""
        ns = _num(r[2])
        if not name or name.lower() == "nan" or ns is None:   # skip section headers / blanks
            continue
        rows.append((ym, name, ns, _num(r[3]), _num(r[4]), _num(r[5]), _num(r[6]), _num(r[7]), _num(r[8])))
    return rows


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.amfiindia.com/"})
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    ensure(conn)

    today = date.today()
    tot = 0
    y, m = 2019, 1
    while (y, m) <= (today.year, today.month):
        ym = f"{y}-{m:02d}"
        url = f"https://portal.amfiindia.com/spages/am{MONTHS[m-1]}{y}repo.xls"
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 5000:
                rows = parse_report(r.content, ym)
                if rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO mf_industry_monthly VALUES (?,?,?,?,?,?,?,?,?)", rows)
                    conn.commit()
                    tot += len(rows)
                print(f"  {ym}: {len(rows)} categories", flush=True)
            else:
                print(f"  {ym}: HTTP {r.status_code}", flush=True)
        except Exception as e:
            print(f"  {ym}: ERR {str(e)[:40]}", flush=True)
        time.sleep(0.4)
        m += 1
        if m > 12:
            m, y = 1, y + 1

    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT report_month) FROM mf_industry_monthly").fetchone()
    conn.close()
    print(f"DONE: mf_industry_monthly {n[0]:,} rows, {n[1]} months", flush=True)


if __name__ == "__main__":
    main()
