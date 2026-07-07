#!/usr/bin/env python3
"""build_regime_spine.py — Part 2 Module 1: multi-axis daily macro regime spine.

Replaces the regime_align breadth placeholder with a transparent, rule-based state
vector. Deliberately NOT an HMM (documented to overfit daily data); every axis is a
bounded [-100,100] score derived from trailing-only transforms of series already in
the warehouse, so the whole spine is PIT-correct and auditable.

Axes (per trading day):
  risk_axis       NIFTY & SPX distance above 200DMA + breadth %>200DMA (centered)
  vol_axis        IndiaVIX + US VIX trailing-1yr percentile (low vol = +)
  fx_axis         INR strength (USDINR below its 200DMA = +) and DXY weakness (+)
                  -- SHORT-horizon axis only (FX->equity link is short-run/sectoral)
  commodity_axis  Brent below trend (+, India imports oil), Copper above trend (+,
                  global growth), Gold below trend (+, fear off)
  rates_axis      US10Y and India10Y yields below their own trend (+)
  flow_axis       FII net index-futures positioning percentile -- CONTEXT ONLY
                  (FII flows are trend-chasing/lagging per the causality evidence);
                  weight kept tiny.

regime_score (0..100) = weighted mean of available axes mapped from [-100,100];
weights renormalised over non-NaN axes per day. regime_label: >=60 risk_on,
<=40 risk_off, else neutral.

The spine DOES NOT feed scoring until common/backtest_regime_spine.py proves it
beats the incumbent 4-vote gate out-of-sample (ship gate, doc Module 1).

Idempotent full rebuild. Run:  py -3.14 macro/build_regime_spine.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
AXIS_VERSION = "v1.0"

# axis weights (priors; validation decides if the spine ships at all)
AXIS_WEIGHTS = {"risk_axis": 0.40, "vol_axis": 0.25, "fx_axis": 0.10,
                "commodity_axis": 0.10, "rates_axis": 0.10, "flow_axis": 0.05}

DDL = """CREATE TABLE IF NOT EXISTS regime_daily (
    date TEXT PRIMARY KEY,
    risk_axis REAL, vol_axis REAL, fx_axis REAL,
    commodity_axis REAL, rates_axis REAL, flow_axis REAL,
    regime_score REAL,          -- 0..100, feeds regime_align IF validation ships it
    regime_label TEXT,          -- risk_on | neutral | risk_off
    axis_version TEXT, computed_at TEXT
)"""


def dist200(px, cap):
    """% distance from own 200DMA, clipped to +-cap, scaled to +-100. Trailing only."""
    ma = px.rolling(200).mean()
    return ((px / ma - 1).clip(-cap, cap) / cap * 100)


def trailing_pctile(s, window=252):
    """Rolling percentile rank of the latest value within the trailing window (0..1)."""
    return s.rolling(window).apply(lambda w: (w <= w[-1]).mean(), raw=True)


def load_series(conn, symbol):
    d = pd.read_sql("SELECT date,close FROM global_indices_daily WHERE symbol=? ORDER BY date",
                    conn, params=(symbol,))
    return d.set_index("date")["close"]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute(DDL)

    s = {sym: load_series(conn, sym) for sym in
         ["NIFTY50", "SPX", "IndiaVIX", "VIX", "USDINR", "DXY",
          "BrentCrude", "Copper", "Gold", "US10Y"]}
    breadth = pd.read_sql("SELECT date,pct_above_200dma FROM market_breadth ORDER BY date",
                          conn).set_index("date")["pct_above_200dma"]
    in10 = pd.read_sql("SELECT date,yield_10y FROM india_bond_yields ORDER BY date",
                       conn).set_index("date")["yield_10y"]
    poi = pd.read_sql("SELECT date,index_fut_long,index_fut_short FROM participant_oi "
                      "WHERE category LIKE 'FII%' ORDER BY date", conn)

    # calendar = NIFTY trading days (the spine is an Indian-market state vector)
    cal = s["NIFTY50"].index

    def align(series):
        """As-of align any series onto the NIFTY calendar (forward-fill, trailing only)."""
        return series.reindex(series.index.union(cal)).sort_index().ffill().reindex(cal)

    # ---- risk: India + global equity trend and breadth ----
    risk = pd.concat([dist200(s["NIFTY50"], 0.15),
                      align(dist200(s["SPX"], 0.15)),
                      align(((breadth - 50) * 2).clip(-100, 100))], axis=1).mean(axis=1)

    # ---- vol: low VIX percentile = risk-on ----
    vol = pd.concat([100 - 200 * trailing_pctile(s["IndiaVIX"]).reindex(cal),
                     align(100 - 200 * trailing_pctile(s["VIX"]))], axis=1).mean(axis=1)

    # ---- fx: INR strength & weak dollar are supportive (short-horizon) ----
    fx = pd.concat([align(-dist200(s["USDINR"], 0.05)),
                    align(-dist200(s["DXY"], 0.05))], axis=1).mean(axis=1)

    # ---- commodities: cheap oil (+, importer), copper up (+, growth), gold down (+) ----
    cmd = pd.concat([align(-dist200(s["BrentCrude"], 0.20)),
                     align(dist200(s["Copper"], 0.20)),
                     align(-dist200(s["Gold"], 0.20))], axis=1).mean(axis=1)

    # ---- rates: falling yields are supportive ----
    in10_trend = -((in10 / in10.rolling(12, min_periods=6).median() - 1)
                   .clip(-0.10, 0.10) / 0.10 * 100)          # monthly series
    rates = pd.concat([align(-dist200(s["US10Y"], 0.15)),
                       align(in10_trend)], axis=1).mean(axis=1)

    # ---- flows (context only): FII net index-futures share, trailing percentile ----
    poi["net_share"] = ((poi["index_fut_long"] - poi["index_fut_short"])
                        / (poi["index_fut_long"] + poi["index_fut_short"]).replace(0, np.nan))
    fii = poi.set_index("date")["net_share"]
    flow = align(200 * trailing_pctile(fii) - 100)

    axes = pd.DataFrame({"risk_axis": risk, "vol_axis": vol, "fx_axis": fx,
                         "commodity_axis": cmd, "rates_axis": rates, "flow_axis": flow})

    # composite: weight-renormalised over available axes -> 0..100 score
    w = pd.Series(AXIS_WEIGHTS)
    weighted = axes.mul(w, axis=1)
    wsum = axes.notna().mul(w, axis=1).sum(axis=1)
    comp = weighted.sum(axis=1, skipna=True) / wsum.replace(0, np.nan)
    score = ((comp + 100) / 2).clip(0, 100)
    label = pd.cut(score, [-1, 40, 60, 101], labels=["risk_off", "neutral", "risk_on"])

    out = axes.copy()
    out["regime_score"] = score
    out["regime_label"] = label.astype(str)
    out = out.dropna(subset=["risk_axis", "regime_score"])
    now = datetime.now().isoformat()

    conn.execute("DELETE FROM regime_daily")
    conn.executemany(
        "INSERT OR REPLACE INTO regime_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(d, *[None if pd.isna(v) else round(float(v), 2) for v in
               (r.risk_axis, r.vol_axis, r.fx_axis, r.commodity_axis,
                r.rates_axis, r.flow_axis, r.regime_score)],
          r.regime_label, AXIS_VERSION, now) for d, r in out.iterrows()])
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM regime_daily").fetchone()[0]
    lab = dict(conn.execute("SELECT regime_label,COUNT(*) FROM regime_daily GROUP BY 1"))
    last = conn.execute("SELECT date,regime_score,regime_label FROM regime_daily "
                        "ORDER BY date DESC LIMIT 1").fetchone()
    print(f"  regime_daily: {n:,} days  ({out.index.min()} -> {out.index.max()})", flush=True)
    print(f"  label mix: {lab}", flush=True)
    print(f"  latest: {last[0]}  score {last[1]:.1f}  {last[2]}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
