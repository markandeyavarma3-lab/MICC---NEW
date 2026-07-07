#!/usr/bin/env python3
"""monitor.py — PHASE 7: monitoring, data-quality & governance health-check.

One pass over the warehouse + research/product layer that flags issues a solo
operator must catch: stale data, data-quality breaks, regime flips, and strategy
health. Writes `monitoring_log(ts, check, status, detail)` and prints a report with
OK / WARN / ALERT. Run daily (it's wired into run_pipeline if desired).

Run:  py -3.14 common/monitor.py
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
STALE_DAYS = 6        # flag a daily table older than this many calendar days


def main():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA busy_timeout=60000")
    q = lambda s, p=(): c.execute(s, p).fetchone()
    out = []
    def log(status, check, detail=""):
        out.append((status, check, detail))

    today = datetime.now().date()

    # 1) DATA FRESHNESS
    for tbl, col in [("stock_data", "date"), ("fo_data", "date"),
                     ("mf_nav_history", "date"), ("bulk_deals", "date")]:
        mx = q(f"SELECT MAX({col}) FROM {tbl}")[0]
        if not mx:
            log("ALERT", f"freshness {tbl}", "no data"); continue
        age = (today - datetime.strptime(mx[:10], "%Y-%m-%d").date()).days
        log("OK" if age <= STALE_DAYS else "WARN", f"freshness {tbl}", f"latest {mx[:10]} ({age}d old)")

    # 2) DATA QUALITY
    neg = q("SELECT COUNT(*) FROM stock_data WHERE close<=0 OR close IS NULL")[0]
    log("OK" if neg == 0 else "ALERT", "stock_data prices valid", f"{neg} bad rows")
    nadj = q("SELECT COUNT(*) FROM stock_data_adj WHERE close<=0")[0]
    log("OK" if nadj == 0 else "ALERT", "adjusted prices valid", f"{nadj} bad rows")
    uni = q("SELECT COUNT(*) FROM pit_universe WHERE rebal_date=(SELECT MAX(rebal_date) FROM pit_universe) AND top500=1")[0]
    log("OK" if 400 <= uni <= 500 else "WARN", "universe size sane", f"{uni} top500 latest")

    # 3) REGIME STATE + FLIP
    br = c.execute("SELECT date,pct_above_200dma FROM market_breadth ORDER BY date DESC LIMIT 22").fetchall()
    if br:
        cur = br[0][1]
        prev = br[21][1] if len(br) > 21 else cur
        state = "RISK-ON" if cur >= 50 else "RISK-OFF"
        flip = (cur >= 50) != (prev >= 50)
        log("WARN" if flip else "OK", "market regime",
            f"{state} (%>200DMA {cur:.0f}, ~1mo ago {prev:.0f})" + (" — FLIPPED" if flip else ""))

    # 4) STRATEGY HEALTH
    sh = q("SELECT value FROM bt_strategy_metrics WHERE strategy='momentum_delivery_lowvol' AND metric='Sharpe'")
    log("OK" if sh and sh[0] > 1.0 else "WARN", "flagship strategy Sharpe",
        f"{sh[0]:.2f}" if sh else "missing")
    pn = q("SELECT date,nav FROM paper_nav ORDER BY date DESC LIMIT 1")
    log("OK" if pn else "WARN", "paper portfolio", f"NAV Rs {pn[1]:,.0f} @ {pn[0]}" if pn else "no paper run")
    nstrat = q("SELECT COUNT(DISTINCT strategy) FROM bt_strategy_metrics")[0]
    log("OK" if nstrat >= 8 else "WARN", "strategy library", f"{nstrat} strategies")

    # 5) SECTOR coverage governance
    cov = q("SELECT COUNT(DISTINCT p.symbol) FROM pit_universe p JOIN dim_sector d ON p.symbol=d.symbol WHERE p.top500=1")[0]
    tot = q("SELECT COUNT(DISTINCT symbol) FROM pit_universe WHERE top500=1")[0]
    log("OK" if cov / tot > 0.6 else "WARN", "sector coverage", f"{cov}/{tot} ({cov/tot*100:.0f}%)")

    # persist + report
    ts = datetime.now().isoformat()
    c.execute("""CREATE TABLE IF NOT EXISTS monitoring_log (
        ts TEXT, check_name TEXT, status TEXT, detail TEXT)""")
    c.executemany("INSERT INTO monitoring_log VALUES (?,?,?,?)",
                  [(ts, ch, st, dt) for st, ch, dt in out])
    c.commit()

    n_alert = sum(1 for s, _, _ in out if s == "ALERT")
    n_warn = sum(1 for s, _, _ in out if s == "WARN")
    print("=" * 64)
    print(f"  MICC MONITOR — {ts[:19]}")
    print("=" * 64)
    for st, ch, dt in out:
        tag = {"OK": " OK ", "WARN": "WARN", "ALERT": "!!!!"}[st]
        print(f"  [{tag}] {ch:30} {dt}")
    print("=" * 64)
    print(f"  {len(out)} checks | {n_alert} ALERT | {n_warn} WARN")
    print("=" * 64)
    c.close()


if __name__ == "__main__":
    main()
