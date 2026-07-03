#!/usr/bin/env python3
"""integrate_screener_pit.py — Part 3 Module D(b): PIT-tag + validate the scraped
screener.in annual fundamentals, and compute per-symbol depth for the cap-lift.

PIT discipline (the whole point):
  * report_date = fiscal-year end (e.g. 'Mar 2015' -> 2015-03-31)
  * pit_date    = FY-end + 60 days (SEBI LODR filing-window convention),
    pit_estimated=1 — we do NOT know the true filing date for old years, so we
    lag conservatively. Restated-vs-as-reported risk remains and is why the
    value/quality cap does NOT lift automatically (see below).

Validation vs known-good: for symbols present in annual_income (yfinance era,
2021+), compare screener Net Profit against yfinance net income for overlapping
fiscal years; a symbol is 'validated' when >=1 overlap year matches within 25%
(consolidated-vs-standalone and restatement differences are expected noise).

Outputs:
  fundamentals_annual_pit  (symbol, fiscal_year, report_date, pit_date,
                            pit_estimated, metric, value, source)
  fundamentals_depth       (symbol, depth_years, validated, cap_lift_eligible)

CAP-LIFT PLUMBING, NOT CAP-LIFT: scoring keeps clamping value/quality to <=70.
The A3 cap consults fundamentals_depth ONLY if score_weights contains an
approved '_cap_lift_enabled' row — which requires the value/quality re-backtest
on this extended history to clear its pre-registered bar first (rule_change_log).

Idempotent. Run:  py -3.14 events/integrate_screener_pit.py
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
FILING_LAG_DAYS = 60
VALIDATE_TOL = 0.25
# screener P&L fields worth keeping as metrics (raw names as parsed)
KEEP_FIELDS = {"Sales", "Expenses", "Operating Profit", "OPM %", "Other Income",
               "Interest", "Depreciation", "Profit before tax", "Net Profit",
               "EPS in Rs", "Revenue", "Financing Profit", "Financing Margin %"}

DDL = ["""CREATE TABLE IF NOT EXISTS fundamentals_annual_pit (
    symbol TEXT, fiscal_year TEXT, report_date TEXT, pit_date TEXT,
    pit_estimated INTEGER, metric TEXT, value REAL, source TEXT,
    PRIMARY KEY (symbol, fiscal_year, metric))""",
       """CREATE TABLE IF NOT EXISTS fundamentals_depth (
    symbol TEXT PRIMARY KEY, depth_years INTEGER, validated INTEGER,
    cap_lift_eligible INTEGER, computed_at TEXT)"""]

MONTH_END = {"Mar": "-03-31", "Jun": "-06-30", "Sep": "-09-30", "Dec": "-12-31"}


def fy_dates(fy):
    """'Mar 2015' -> (report_date, pit_date)."""
    mon, yr = fy.split()
    rd = f"{yr}{MONTH_END.get(mon, '-03-31')}"
    pit = (datetime.fromisoformat(rd) + timedelta(days=FILING_LAG_DAYS)).strftime("%Y-%m-%d")
    return rd, pit


def main():
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    for d in DDL:
        conn.execute(d)
    now = datetime.now().isoformat()

    rows = conn.execute("SELECT symbol, fiscal_year, field, value FROM screener_annual "
                        "WHERE field IN ({})".format(",".join("?" * len(KEEP_FIELDS))),
                        tuple(KEEP_FIELDS)).fetchall()
    conn.execute("DELETE FROM fundamentals_annual_pit")
    out = []
    for sym, fy, field, val in rows:
        try:
            rd, pit = fy_dates(fy)
        except Exception:
            continue
        out.append((sym, fy, rd, pit, 1, field, val, "screener.in"))
    conn.executemany("INSERT OR REPLACE INTO fundamentals_annual_pit VALUES (?,?,?,?,?,?,?,?)", out)
    print(f"  fundamentals_annual_pit: {len(out):,} rows", flush=True)

    # ---- validation vs yfinance annual_income (overlap years) ----
    yf = {}
    for sym, rd, js in conn.execute("SELECT symbol, report_date, data_json FROM annual_income"):
        try:
            d = json.loads(js)
            ni = d.get("Net Income From Continuing Operation Net Minority Interest") \
                or d.get("Net Income")
            if ni:
                yf.setdefault(sym, {})[rd[:4]] = ni / 1e7      # rupees -> crore
        except Exception:
            pass

    scr = {}
    for sym, fy, rd, pit, est, field, val, src in out:
        if field == "Net Profit":
            scr.setdefault(sym, {})[rd[:4]] = val              # screener is in crore

    validated = {}
    for sym, years in scr.items():
        ok = 0
        for y, v in years.items():
            ref = yf.get(sym, {}).get(y)
            if ref and abs(ref) > 1 and abs(v - ref) / abs(ref) <= VALIDATE_TOL:
                ok += 1
        validated[sym] = 1 if ok >= 1 else 0

    conn.execute("DELETE FROM fundamentals_depth")
    dep_rows = []
    for sym, years in scr.items():
        depth = len(years)
        v = validated.get(sym, 0)
        dep_rows.append((sym, depth, v, 1 if (depth >= 8 and v) else 0, now))
    conn.executemany("INSERT OR REPLACE INTO fundamentals_depth VALUES (?,?,?,?,?)", dep_rows)
    conn.commit()

    n_dep = len(dep_rows)
    n_val = sum(1 for r in dep_rows if r[2])
    n_elig = sum(1 for r in dep_rows if r[3])
    print(f"  fundamentals_depth: {n_dep} symbols | validated {n_val} | "
          f"cap_lift_eligible (>=8yr AND validated) {n_elig}", flush=True)
    lift = conn.execute("SELECT COUNT(*) FROM score_weights WHERE pillar='_cap_lift_enabled'"
                        ).fetchone()[0]
    print(f"  cap-lift switch: {'ENABLED' if lift else 'OFF (value re-backtest must clear first)'}",
          flush=True)
    conn.close()


if __name__ == "__main__":
    main()
