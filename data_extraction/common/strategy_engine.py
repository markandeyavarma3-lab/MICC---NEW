#!/usr/bin/env python3
"""strategy_engine.py — PHASE 1: generic signal-table strategy & backtest engine.

The foundation for the strategy library (Phase 2) and paper-trading (Phase 3). A
strategy is a function(panel) -> signal table [rebal_date, symbol, weight]; the
generic engine consumes ANY signal table + realized returns + an optional regime
gate, and writes standard output tables:
  bt_portfolio_daily (strategy, date, gross, net, net_gated, turnover, equity)
  bt_trades          (strategy, date, symbol, side, dweight)
  bt_holdings        (strategy, date, symbol, weight)
  bt_strategy_metrics(strategy, metric, value)

Strategy #1 (the validated flagship: momentum + delivery + low-vol composite,
inverse-vol weighted, macro-regime gated) is ported in as the first registry entry.

Run:  py -3.14 common/strategy_engine.py            # run all registered strategies
      py -3.14 common/strategy_engine.py --list      # list strategies
"""
import sqlite3
import sys

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_best import regime_score

SIGNALS = ["mom_12_1", "prox_52w_high", "deliv_1m"]


# ============================ generic engine ============================
def run_engine(name, signal_df, panel, gate=None, cost=COST_PER_SIDE):
    """signal_df: [rebal_date, symbol, weight] target weights (renormalized per date).
    gate: optional Series rebal_date -> 1/0 (invest/cash). Returns dict of outputs."""
    df = signal_df.merge(panel[["rebal_date", "symbol", "realized"]],
                         on=["rebal_date", "symbol"], how="left").dropna(subset=["realized"])
    rebals = sorted(df["rebal_date"].unique())
    prev_w, port, trades, holds = {}, [], [], []
    for R in rebals:
        g = df[df["rebal_date"] == R]
        w = g.set_index("symbol")["weight"]
        w = w[w > 0]
        if w.sum() <= 0:
            continue
        w = w / w.sum()
        gross = float((w * g.set_index("symbol")["realized"]).sum())
        syms = set(w.index) | set(prev_w)
        turn = sum(abs(w.get(s, 0.0) - prev_w.get(s, 0.0)) for s in syms)
        net = gross - turn * cost
        on = 1.0 if (gate is None or gate.get(R, 1) >= 1) else 0.0
        port.append({"date": R, "gross": gross, "net": net, "net_gated": net * on, "turnover": turn})
        for s in syms:
            dw = w.get(s, 0.0) - prev_w.get(s, 0.0)
            if abs(dw) > 1e-6:
                trades.append({"date": R, "symbol": s, "side": "BUY" if dw > 0 else "SELL",
                               "dweight": round(dw, 5)})
        for s, wt in w.items():
            holds.append({"date": R, "symbol": s, "weight": round(float(wt), 5)})
        prev_w = w.to_dict()
    pf = pd.DataFrame(port)
    pf["equity"] = (1 + pf["net_gated"]).cumprod()
    return {"name": name, "portfolio": pf, "trades": pd.DataFrame(trades),
            "holdings": pd.DataFrame(holds), "metrics": metrics(pf["net_gated"])}


# ============================ strategy builders ============================
def _decile(panel, col):
    def f(x):
        v = x.dropna()
        if len(v) < N_DECILES:                # too few names this date -> no signal
            return pd.Series(np.nan, index=x.index)
        return pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1
    return panel.groupby("rebal_date")[col].transform(f)


def strat_momentum_delivery_lowvol(panel):
    """Flagship: composite of mom_12_1 + prox_52w_high + deliv_1m + low_vol,
    long top decile, inverse-vol weighted."""
    p = panel.copy()
    p["low_vol"] = -p["vol_3m"]
    facs = SIGNALS + ["low_vol"]
    p["composite"] = pd.concat(
        [p.groupby("rebal_date")[f].rank(pct=True) for f in facs], axis=1).mean(axis=1)
    p["dec"] = _decile(p, "composite")
    top = p[p["dec"] == N_DECILES].copy()
    iv = 1.0 / top["vol_3m"].clip(lower=0.05)
    top["weight"] = iv
    return top[["rebal_date", "symbol", "weight"]]


def strat_low_volatility(panel):
    """Defensive: long the lowest-realized-vol decile, inverse-vol weighted."""
    p = panel.copy()
    p["dec"] = p.groupby("rebal_date")["vol_3m"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)
    top = p[p["dec"] == 1].copy()                 # decile 1 = lowest vol
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


def strat_short_term_reversal(panel):
    """Contrarian: long the bottom decile of 1-month return (recent losers)."""
    p = panel.copy()
    p["dec"] = _decile(p, "ret_1m")
    top = p[p["dec"] == 1].copy()                 # bottom decile of 1m return
    top["weight"] = 1.0
    return top[["rebal_date", "symbol", "weight"]]


def strat_high52_breakout(panel):
    """Trend/breakout: long top-decile 52-week-high proximity among names above 200DMA."""
    p = panel[panel["above_200"] == 1].copy()
    p["dec"] = _decile(p, "prox_52w_high")
    top = p[p["dec"] == N_DECILES].copy()
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


def strat_dividend_yield(panel):
    """Income: long top-decile trailing-12m dividend yield, inverse-vol weighted."""
    p = panel.dropna(subset=["div_yield"]).copy()
    p = p[p["div_yield"] > 0]
    p["dec"] = _decile(p, "div_yield")
    top = p[p["dec"] == N_DECILES].copy()
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


def strat_sector_rotation(panel, top_k=3):
    """Rotation: long inverse-vol-weighted stocks in the top-K sectors by 12-1 momentum."""
    p = panel.dropna(subset=["sector", "mom_12_1"]).copy()
    sm = p.groupby(["rebal_date", "sector"])["mom_12_1"].mean().reset_index(name="secmom")
    sm["rk"] = sm.groupby("rebal_date")["secmom"].rank(ascending=False)
    top = p.merge(sm[sm["rk"] <= top_k][["rebal_date", "sector"]],
                  on=["rebal_date", "sector"], how="inner").copy()
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


def strat_value_earnings_yield(panel):
    """Value: long top-decile earnings yield (E/P) among positive earners, inverse-vol weighted.
    Uses PIT fundamentals (annual EPS as-of filing) -> ~2021+ history."""
    p = panel.dropna(subset=["earnings_yield"]).copy()
    p = p[p["earnings_yield"] > 0]
    p["dec"] = _decile(p, "earnings_yield")
    top = p[p["dec"] == N_DECILES].copy()
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


def strat_quality_roe(panel):
    """Quality: long top-decile ROE, inverse-vol weighted. PIT annual fundamentals (~2021+)."""
    p = panel.dropna(subset=["roe"]).copy()
    p["dec"] = _decile(p, "roe")
    top = p[p["dec"] == N_DECILES].copy()
    top["weight"] = 1.0 / top["vol_3m"].clip(lower=0.05)
    return top[["rebal_date", "symbol", "weight"]]


REGISTRY = {
    "momentum_delivery_lowvol": strat_momentum_delivery_lowvol,
    "low_volatility": strat_low_volatility,
    "short_term_reversal": strat_short_term_reversal,
    "high52_breakout": strat_high52_breakout,
    "value_earnings_yield": strat_value_earnings_yield,
    "quality_roe": strat_quality_roe,
    "dividend_yield": strat_dividend_yield,
    "sector_rotation": strat_sector_rotation,
}


# ============================ runner ============================
def main():
    if "--list" in sys.argv:
        print("Registered strategies:")
        for k in REGISTRY:
            print("  -", k)
        return

    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + features + regime ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    aux = pd.read_sql("SELECT rebal_date,symbol,vol_3m,med_turnover,ret_1m,dist_sma200,"
                      "above_200 FROM features_monthly", conn)
    panel = panel.merge(aux, on=["rebal_date", "symbol"], how="left").dropna(subset=["vol_3m"])
    panel = panel[panel["top500"] == 1].copy()

    # attach PIT fundamentals as-of (earnings yield, ROE) — no lookahead (pit_date <= rebal_date).
    # panel already carries 'close' (rebalance adjusted close) from load_panel.
    ff = pd.read_sql("SELECT symbol, pit_date, eps, roe FROM fundamentals_features "
                     "WHERE pit_date IS NOT NULL", conn)
    ff["_pd"] = pd.to_datetime(ff["pit_date"], errors="coerce")
    ff = ff.dropna(subset=["_pd"]).sort_values("_pd")
    panel["_rd"] = pd.to_datetime(panel["rebal_date"])
    panel = panel.sort_values("_rd").reset_index(drop=True)
    panel = pd.merge_asof(panel, ff[["_pd", "symbol", "eps", "roe"]], by="symbol",
                          left_on="_rd", right_on="_pd", direction="backward")
    panel["earnings_yield"] = panel["eps"] / panel["close"].where(panel["close"] > 0)
    panel = panel.drop(columns=["_rd", "_pd"]).sort_values(["symbol", "rebal_date"]).reset_index(drop=True)

    # attach sector (dim_sector) + trailing-12m dividend yield
    sec = pd.read_sql("SELECT symbol, sector FROM dim_sector WHERE sector IS NOT NULL", conn)
    panel = panel.merge(sec, on="symbol", how="left")
    divs = pd.read_sql("SELECT symbol,date,amount FROM corporate_actions "
                       "WHERE action_type='DIVIDEND' AND amount>0", conn)
    divs["dt"] = pd.to_datetime(divs["date"], errors="coerce")
    divs = divs.dropna(subset=["dt"]).sort_values(["symbol", "dt"])
    dmap = {s: g for s, g in divs.groupby("symbol")}
    rdt = pd.to_datetime(panel["rebal_date"]).to_numpy()
    ttm = np.zeros(len(panel))
    for sym, idx in panel.groupby("symbol").indices.items():
        g = dmap.get(sym)
        if g is None:
            continue
        dd = g["dt"].to_numpy()
        cum = np.cumsum(g["amount"].to_numpy())
        rd = rdt[idx]
        hi = np.searchsorted(dd, rd, side="right")
        lo = np.searchsorted(dd, rd - np.timedelta64(365, "D"), side="right")
        hv = np.where(hi > 0, cum[np.clip(hi - 1, 0, len(cum) - 1)], 0.0)
        lv = np.where(lo > 0, cum[np.clip(lo - 1, 0, len(cum) - 1)], 0.0)
        ttm[idx] = np.where(hi > 0, hv - lv, 0.0)
    panel["div_yield"] = ttm / panel["close"].where(panel["close"] > 0)

    score, _ = regime_score(conn, rebals, breadth)
    gate = (score >= 2).astype(float)         # macro regime gate (>=2/4 votes)

    results = []
    for name, builder in REGISTRY.items():
        print(f"Running strategy: {name} ...", flush=True)
        sig = builder(panel)
        results.append(run_engine(name, sig, panel, gate=gate))

    # persist standard output tables
    allpf = pd.concat([r["portfolio"].assign(strategy=r["name"]) for r in results], ignore_index=True)
    alltr = pd.concat([r["trades"].assign(strategy=r["name"]) for r in results], ignore_index=True)
    allhd = pd.concat([r["holdings"].assign(strategy=r["name"]) for r in results], ignore_index=True)
    met_rows = [(r["name"], k, float(v)) for r in results for k, v in (r["metrics"] or {}).items()]
    for tbl, df in [("bt_portfolio_daily", allpf), ("bt_trades", alltr), ("bt_holdings", allhd)]:
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        df.to_sql(tbl, conn, if_exists="replace", index=False)
    conn.execute("DROP TABLE IF EXISTS bt_strategy_metrics")
    conn.execute("CREATE TABLE bt_strategy_metrics (strategy TEXT, metric TEXT, value REAL)")
    conn.executemany("INSERT INTO bt_strategy_metrics VALUES (?,?,?)", met_rows)
    conn.commit(); conn.close()

    print("\n=== STRATEGY LEADERBOARD (net, regime-gated) ===", flush=True)
    print(f"  {'strategy':32} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7} {'Calmar':>7}", flush=True)
    for r in sorted(results, key=lambda x: -(x["metrics"] or {}).get("Sharpe", -9)):
        m = r["metrics"]
        if m:
            print(f"  {r['name']:32} {m['CAGR']*100:>6.1f}% {m['Sharpe']:>7.2f} "
                  f"{m['Sortino']:>8.2f} {m['MaxDD']*100:>6.1f}% {m['Calmar']:>7.2f}", flush=True)
    print(f"\n  Saved -> bt_portfolio_daily / bt_trades ({len(alltr):,}) / "
          f"bt_holdings ({len(allhd):,}) / bt_strategy_metrics", flush=True)


if __name__ == "__main__":
    main()
