#!/usr/bin/env python3
"""backfill_corporate_actions.py — Corporate actions (dividend / bonus / split /
rights / buyback / interest) from the NSE bulk date-range API. Classifies the
free-text 'subject' into action_type + ratio/amount. Idempotent.

Run:  py -3.14 events/backfill_corporate_actions.py            # from 2010
      py -3.14 events/backfill_corporate_actions.py --from 2005
"""
import sqlite3, re, sys, time
from pathlib import Path
from datetime import date, timedelta, datetime

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
API = ("https://www.nseindia.com/api/corporates-corporateActions"
       "?index=equities&from_date={f}&to_date={t}")


def sess():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


def classify(subject):
    s = (subject or "").lower()
    at, ratio, amount = "OTHER", None, None
    if "dividend" in s:
        at = "DIVIDEND"
        m = re.search(r"rs\.?\s*([\d.]+)", s)
        amount = float(m.group(1)) if m else None
    elif "bonus" in s:
        at = "BONUS"
        m = re.search(r"(\d+\s*:\s*\d+)", subject)
        ratio = m.group(1).replace(" ", "") if m else None
    elif "split" in s or "sub-division" in s or "subdivision" in s:
        at = "SPLIT"
        nums = re.findall(r"(?:rs|re)\.?\s*([\d.]+)", s)
        if len(nums) >= 2:
            ratio = f"{nums[0]}:{nums[1]}"
    elif "rights" in s:
        at = "RIGHTS"
        m = re.search(r"(\d+\s*:\s*\d+)", subject)
        ratio = m.group(1).replace(" ", "") if m else None
    elif "buy" in s and "back" in s:
        at = "BUYBACK"
    elif "interest" in s:
        at = "INTEREST"
    elif "redemption" in s:
        at = "REDEMPTION"
    elif "agm" in s or "annual general" in s:
        at = "AGM"
    return at, ratio, amount


def main():
    year_from = 2010
    if "--from" in sys.argv:
        year_from = int(sys.argv[sys.argv.index("--from") + 1])

    s = sess()
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    # recreate (was empty, no usable key)
    conn.execute("DROP TABLE IF EXISTS corporate_actions")
    conn.execute("""CREATE TABLE corporate_actions (
        symbol TEXT, date TEXT, action_type TEXT, ratio TEXT, amount REAL, subject TEXT,
        PRIMARY KEY(symbol, date, action_type, subject))""")
    conn.execute("CREATE INDEX idx_ca_symbol ON corporate_actions(symbol)")
    conn.commit()

    cur, end, total = date(year_from, 1, 1), date.today(), 0
    while cur <= end:
        nxt = (date(cur.year + cur.month // 12, cur.month % 12 + 1, 1) - timedelta(days=1))
        nxt = min(nxt, end)
        url = API.format(f=cur.strftime("%d-%m-%Y"), t=nxt.strftime("%d-%m-%Y"))
        try:
            d = s.get(url, timeout=30).json()
            recs = d if isinstance(d, list) else d.get("data", [])
            rows = []
            for r in recs:
                try:
                    dt = datetime.strptime(r.get("exDate", ""), "%d-%b-%Y").strftime("%Y-%m-%d")
                except Exception:
                    continue
                sub = r.get("subject", "") or ""
                at, ratio, amount = classify(sub)
                rows.append((r.get("symbol"), dt, at, ratio, amount, sub))
            if rows:
                conn.executemany("INSERT OR REPLACE INTO corporate_actions "
                                 "(symbol,date,action_type,ratio,amount,subject) VALUES (?,?,?,?,?,?)", rows)
                conn.commit()
                total += len(rows)
            print(f"  {cur.strftime('%Y-%m')}: {len(rows)} ({total:,} total)", flush=True)
        except Exception as e:
            print(f"  {cur.strftime('%Y-%m')}: err {str(e)[:50]}", flush=True)
        time.sleep(0.4)
        cur = nxt + timedelta(days=1)

    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(date),MAX(date) FROM corporate_actions").fetchone()
    conn.close()
    print(f"DONE: corporate_actions {n[0]:,} rows, {n[1]:,} symbols, {n[2]} -> {n[3]}", flush=True)


if __name__ == "__main__":
    main()
