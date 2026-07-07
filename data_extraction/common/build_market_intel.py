#!/usr/bin/env python3
"""build_market_intel.py — deals + F&O positioning intelligence (dashboard feeds).

Writes two compact tables the dashboard reads:
  deals_intel  -- recent insider CLUSTER buys + bulk-deal accumulation (smart-money)
  fno_intel    -- futures buildup quadrant + PCR extremes on the ~210 F&O names

Factual analytics from disclosed data. Not investment advice.
Run:  py -3.14 common/build_market_intel.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def deals_intel(conn):
    rows = []
    # insider cluster buys (last 120d): >=3 distinct insiders acquiring
    ins = pd.read_sql(
        "SELECT symbol, COUNT(DISTINCT name) nb, SUM(CASE WHEN value>0 THEN value ELSE 0 END) val "
        "FROM insider_trading WHERE filing_date >= date((SELECT MAX(filing_date) FROM insider_trading),'-120 day') "
        "AND transaction_type LIKE '%Buy%' GROUP BY symbol HAVING nb>=3 ORDER BY nb DESC LIMIT 12", conn)
    for _, r in ins.iterrows():
        rows.append(("Insider cluster-buy", r["symbol"], f"{int(r['nb'])} insiders",
                     float(r["val"]), "120d"))
    # bulk-deal net accumulation (last 30d)
    bd = pd.read_sql(
        "SELECT symbol, SUM(CASE WHEN buy_sell LIKE 'B%' THEN qty*price ELSE -qty*price END) net "
        "FROM bulk_deals WHERE date >= date((SELECT MAX(date) FROM bulk_deals),'-30 day') "
        "GROUP BY symbol ORDER BY net DESC LIMIT 10", conn)
    for _, r in bd.iterrows():
        if r["net"] > 0:
            rows.append(("Bulk-deal accumulation", r["symbol"], "net buy", float(r["net"]), "30d"))
    df = pd.DataFrame(rows, columns=["category", "symbol", "detail", "value", "window"])
    conn.execute("DROP TABLE IF EXISTS deals_intel")
    df.to_sql("deals_intel", conn, if_exists="replace", index=False)
    return df


def fno_intel(conn):
    D = conn.execute("SELECT MAX(date) FROM fo_data WHERE instrument IN ('STF','FUTSTK')").fetchone()[0]
    fut = pd.read_sql(
        "SELECT symbol, expiry, open_int, chg_in_oi FROM fo_data "
        "WHERE instrument IN ('STF','FUTSTK') AND date=? AND open_int IS NOT NULL", conn, params=(D,))
    # total futures OI across all live expiries (robust to expiry-week rollover,
    # where front-month OI collapses as positions roll to the next series)
    fut = fut[fut["expiry"] >= D]
    oi = fut.groupby("symbol").agg(oi=("open_int", "sum"), doi=("chg_in_oi", "sum")).reset_index()

    # price direction from underlying (last 2 trading days)
    d2 = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM stock_data ORDER BY date DESC LIMIT 2").fetchall()]
    px = pd.read_sql(f"SELECT symbol,date,close FROM stock_data WHERE date IN ('{d2[0]}','{d2[1]}')", conn)
    px = px.pivot(index="symbol", columns="date", values="close")
    px["ret"] = px[d2[0]] / px[d2[1]] - 1
    oi = oi.merge(px.reset_index()[["symbol", "ret"]], on="symbol", how="left").dropna(subset=["ret"])

    def quad(r):
        if r["doi"] > 0 and r["ret"] > 0: return "Long buildup"
        if r["doi"] > 0 and r["ret"] < 0: return "Short buildup"
        if r["doi"] < 0 and r["ret"] > 0: return "Short covering"
        return "Long unwinding"
    oi["signal"] = oi.apply(quad, axis=1)
    oi["oi_chg_pct"] = oi["doi"] / (oi["oi"] - oi["doi"]).replace(0, np.nan) * 100

    pcr = pd.read_sql("SELECT symbol, pcr_oi, total_oi FROM options_pcr_daily "
                      "WHERE date=(SELECT MAX(date) FROM options_pcr_daily) AND total_oi>0", conn)

    rows = []
    lb = oi[oi["signal"] == "Long buildup"].sort_values("oi_chg_pct", ascending=False).head(6)
    sb = oi[oi["signal"] == "Short buildup"].sort_values("oi_chg_pct", ascending=False).head(6)
    for _, r in lb.iterrows():
        rows.append(("Long buildup (bullish)", r["symbol"], f"OI +{r['oi_chg_pct']:.0f}%",
                     float(r["ret"] * 100), D))
    for _, r in sb.iterrows():
        rows.append(("Short buildup (bearish)", r["symbol"], f"OI +{r['oi_chg_pct']:.0f}%",
                     float(r["ret"] * 100), D))
    for _, r in pcr.sort_values("pcr_oi", ascending=False).head(5).iterrows():
        rows.append(("High PCR (puts heavy)", r["symbol"], f"PCR {r['pcr_oi']:.2f}", 0.0, D))
    for _, r in pcr[pcr["pcr_oi"] > 0].sort_values("pcr_oi").head(5).iterrows():
        rows.append(("Low PCR (calls heavy)", r["symbol"], f"PCR {r['pcr_oi']:.2f}", 0.0, D))
    df = pd.DataFrame(rows, columns=["category", "symbol", "detail", "value", "asof"])
    conn.execute("DROP TABLE IF EXISTS fno_intel")
    df.to_sql("fno_intel", conn, if_exists="replace", index=False)
    return df, D


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    d = deals_intel(conn)
    f, D = fno_intel(conn)
    conn.commit(); conn.close()
    print(f"deals_intel: {len(d)} rows | fno_intel: {len(f)} rows (F&O asof {D})", flush=True)
    print("  top insider cluster:", d[d.category.str.contains('Insider')].head(1).to_dict("records"))
    print("  top long-buildup:", f[f.category.str.contains('Long buildup')].head(1).to_dict("records"))


if __name__ == "__main__":
    main()
