#!/usr/bin/env python3
"""recommendations.py — trackable stock recommendations + outcome feedback loop.

The accountability layer: turns the strategy's top-conviction picks into explicit
recommendations (entry / target / stop price band + a 1-month duration), logs them,
then after the duration elapses checks the real price path and scores each call
(TARGET-hit / STOP-hit / EXPIRED), building a track record that tells you what is
actually working — so you can improve the model.

Table `recommendations`:
  rec_date, symbol, company, strategy, score, horizon_days, entry, target, stop,
  status(OPEN/CLOSED), close_date, exit_price, realized_return, outcome

Default run = backfill a historical track record + generate today's open calls +
evaluate everything elapsed + print the scorecard.

Run:  py -3.14 common/recommendations.py
      py -3.14 common/recommendations.py --report       # just the scorecard
"""
import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
HORIZON_TD = 21           # 1-month duration (trading days)
N_RECS = 15               # top-N conviction picks per date
TARGET_SIG = 1.5          # target band = entry * (1 + 1.5*sigma_horizon)
STOP_SIG = 1.0            # stop band   = entry * (1 - 1.0*sigma_horizon)
STRATEGY = "momentum_delivery_lowvol"


def composite(df):
    df = df.copy()
    df["low_vol"] = -df["vol_3m"]
    parts = [df.groupby("rebal_date")[f].rank(pct=True)
             for f in ("mom_12_1", "prox_52w_high", "deliv_1m", "low_vol")]
    df["composite"] = pd.concat(parts, axis=1).mean(axis=1)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--backfill", type=int, default=36, help="historical rebalances to seed")
    a = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS recommendations (
        rec_date TEXT, symbol TEXT, company TEXT, strategy TEXT, score REAL,
        horizon_days INTEGER, entry REAL, target REAL, stop REAL, status TEXT,
        close_date TEXT, exit_price REAL, realized_return REAL, outcome TEXT,
        PRIMARY KEY(rec_date, symbol, strategy))""")

    if not a.report:
        feat = pd.read_sql("SELECT rebal_date,symbol,mom_12_1,prox_52w_high,deliv_1m,vol_3m "
                           "FROM features_monthly WHERE top500=1", conn).dropna()
        feat = composite(feat)
        px = pd.read_sql("SELECT symbol,date,open,high,low,close FROM stock_data", conn)
        reg = dict(pd.read_sql("SELECT symbol,company_name FROM stock_registry", conn).values)
        tdates = np.sort(px["date"].unique())
        last_data = tdates[-1]
        rebals = sorted(feat["rebal_date"].unique())

        # --- GENERATE: backfill last N elapsed + today's live calls ---
        gen_dates = rebals[-(a.backfill + 1):]
        closeR = px[["symbol", "date", "close"]].rename(columns={"date": "rebal_date", "close": "entry"})
        rows = []
        for R in gen_dates:
            g = feat[feat["rebal_date"] == R].nlargest(N_RECS, "composite")
            g = g.merge(closeR[closeR["rebal_date"] == R], on=["rebal_date", "symbol"], how="left").dropna(subset=["entry"])
            sig_h = g["vol_3m"] * np.sqrt(HORIZON_TD / 252.0)        # 1-month sigma
            g["target"] = g["entry"] * (1 + TARGET_SIG * sig_h)
            g["stop"] = g["entry"] * (1 - STOP_SIG * sig_h)
            for _, r in g.iterrows():
                rows.append((R, r["symbol"], reg.get(r["symbol"], ""), STRATEGY,
                             round(r["composite"] * 100, 1), HORIZON_TD, round(r["entry"], 2),
                             round(r["target"], 2), round(r["stop"], 2), "OPEN", None, None, None, None))
        conn.executemany("INSERT OR IGNORE INTO recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        print(f"  generated/kept {len(rows)} recommendations across {len(gen_dates)} dates", flush=True)

        # --- EVALUATE: close any OPEN whose horizon has fully elapsed ---
        opens = pd.read_sql("SELECT rowid,* FROM recommendations WHERE status='OPEN'", conn)
        pxg = {s: g.sort_values("date") for s, g in px.groupby("symbol")}
        tpos = {d: i for i, d in enumerate(tdates)}
        upd = []
        for _, r in opens.iterrows():
            R = r["rec_date"]
            if R not in tpos or tpos[R] + HORIZON_TD >= len(tdates):
                continue                                  # not yet elapsed
            end = tdates[tpos[R] + HORIZON_TD]
            g = pxg.get(r["symbol"])
            if g is None:
                continue
            path = g[(g["date"] > R) & (g["date"] <= end)]
            if path.empty:
                continue
            exit_px, exit_dt, outcome = None, None, None
            for _, d in path.iterrows():               # walk forward; first touch wins
                if d["high"] >= r["target"]:
                    exit_px, exit_dt, outcome = r["target"], d["date"], "TARGET"; break
                if d["low"] <= r["stop"]:
                    exit_px, exit_dt, outcome = r["stop"], d["date"], "STOP"; break
            if exit_px is None:                          # neither touched -> expire at horizon close
                last = path.iloc[-1]
                exit_px, exit_dt = last["close"], last["date"]
                outcome = "EXPIRED_WIN" if exit_px > r["entry"] else "EXPIRED_LOSS"
            ret = exit_px / r["entry"] - 1
            upd.append((exit_dt, round(exit_px, 2), round(ret, 4), outcome, r["rowid"]))
        conn.executemany("UPDATE recommendations SET status='CLOSED', close_date=?, exit_price=?, "
                         "realized_return=?, outcome=? WHERE rowid=?", upd)
        conn.commit()
        print(f"  evaluated/closed {len(upd)} elapsed recommendations", flush=True)

    report(conn)
    conn.close()


def report(conn):
    df = pd.read_sql("SELECT * FROM recommendations", conn)
    closed = df[df["status"] == "CLOSED"]
    op = df[df["status"] == "OPEN"]
    print("\n" + "=" * 70)
    print(f"  RECOMMENDATION SCORECARD  ({len(df)} total: {len(closed)} closed, {len(op)} open)")
    print("=" * 70)
    if len(closed):
        win = (closed["realized_return"] > 0).mean()
        avg = closed["realized_return"].mean()
        avg_win = closed.loc[closed["realized_return"] > 0, "realized_return"].mean()
        avg_loss = closed.loc[closed["realized_return"] <= 0, "realized_return"].mean()
        oc = closed["outcome"].value_counts()
        print(f"  hit rate (positive)   : {win*100:.0f}%")
        print(f"  avg return / call     : {avg*100:+.2f}%  (1-month horizon)")
        print(f"  avg win / avg loss    : {avg_win*100:+.2f}% / {avg_loss*100:+.2f}%")
        print(f"  target-hit rate       : {oc.get('TARGET',0)/len(closed)*100:.0f}%   "
              f"stop-hit: {oc.get('STOP',0)/len(closed)*100:.0f}%   "
              f"expired: {(oc.get('EXPIRED_WIN',0)+oc.get('EXPIRED_LOSS',0))/len(closed)*100:.0f}%")
        print("  best/worst closed calls:")
        for _, r in closed.nlargest(3, "realized_return").iterrows():
            print(f"     +{r['realized_return']*100:5.1f}%  {r['symbol']:12} {r['rec_date']} -> {r['outcome']}")
        for _, r in closed.nsmallest(2, "realized_return").iterrows():
            print(f"     {r['realized_return']*100:6.1f}%  {r['symbol']:12} {r['rec_date']} -> {r['outcome']}")
    if len(op):
        latest = op["rec_date"].max()
        print(f"\n  OPEN calls (latest {latest}) — entry / target / stop, 1-month:")
        for _, r in op[op["rec_date"] == latest].head(10).iterrows():
            print(f"     {r['symbol']:12} entry {r['entry']:>9.2f}  target {r['target']:>9.2f} "
                  f"(+{(r['target']/r['entry']-1)*100:.0f}%)  stop {r['stop']:>9.2f} "
                  f"({(r['stop']/r['entry']-1)*100:.0f}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
