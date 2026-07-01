#!/usr/bin/env python3
"""paper_trader.py — PHASE 3: forward paper-trading simulator (the 'trade-it-myself' core).

Unlike the backtest (abstract weights/returns over all history at once), this runs a
STATEFUL virtual portfolio forward in time: real starting capital, INTEGER shares,
a realistic Indian-equity delivery cost model, regime-gated liquidation to cash, and
daily-mark NAV. It then measures LIVE-vs-BACKTEST drift so you know the edge is holding.

Outputs:
  paper_nav       (strategy, date, nav, cash, invested)
  paper_positions (strategy, date, symbol, shares, value)
  paper_trades    (strategy, date, symbol, side, shares, price, cost)

Run:  py -3.14 execution/paper_trader.py                       # flagship, full history
      py -3.14 execution/paper_trader.py --strategy low_volatility --start 2018-01-01 --capital 1000000
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from backtest_momentum import DB_PATH, N_DECILES, load_panel, metrics   # noqa: E402
from backtest_best import regime_score                                   # noqa: E402
from strategy_engine import REGISTRY                                      # noqa: E402

COST_SIDE = 0.0012        # ~0.12%/side: STT + exchange + stamp + GST + slippage (delivery)


def prepare(conn):
    panel, rebals, breadth = load_panel(conn)
    aux = pd.read_sql("SELECT rebal_date,symbol,vol_3m,med_turnover,ret_1m,dist_sma200,"
                      "above_200 FROM features_monthly", conn)
    panel = panel.merge(aux, on=["rebal_date", "symbol"], how="left").dropna(subset=["vol_3m"])
    panel = panel[panel["top500"] == 1].copy()
    score, _ = regime_score(conn, rebals, breadth)
    return panel, rebals, (score >= 2)


def paper_trade(name, panel, rebals, gate, price, start, capital):
    sig = REGISTRY[name](panel)
    sig = sig[sig["weight"] > 0].copy()
    # normalize weights per rebalance
    sig["w"] = sig["weight"] / sig.groupby("rebal_date")["weight"].transform("sum")
    wmap = {R: dict(zip(g["symbol"], g["w"])) for R, g in sig.groupby("rebal_date")}

    dates = [R for R in rebals if R >= start]
    cash, pos = float(capital), {}            # pos: symbol -> shares
    nav_rows, trade_rows, pos_rows = [], [], []
    for R in dates:
        # mark-to-market at R (drop unpriceable/delisted positions = realize at 0)
        pos = {s: sh for s, sh in pos.items() if (R, s) in price}
        invested = sum(sh * price[(R, s)] for s, sh in pos.items())
        nav = cash + invested
        nav_rows.append((name, R, nav, cash, invested))

        # target weights: cash when regime-off, else strategy weights
        tw = {} if not gate.get(R, True) else {s: w for s, w in wmap.get(R, {}).items()
                                               if (R, s) in price}
        target_sh = {s: int((nav * w) // price[(R, s)]) for s, w in tw.items()}

        for s in set(pos) | set(target_sh):
            if (R, s) not in price:
                continue
            d = target_sh.get(s, 0) - pos.get(s, 0)
            if d == 0:
                continue
            px = price[(R, s)]
            cost = abs(d) * px * COST_SIDE
            cash += (-d * px) - cost          # buy(d>0): cash down; sell(d<0): cash up; less cost
            trade_rows.append((name, R, s, "BUY" if d > 0 else "SELL", abs(d), round(px, 2), round(cost, 2)))
        pos = {s: sh for s, sh in target_sh.items() if sh > 0}
        for s, sh in pos.items():
            pos_rows.append((name, R, s, sh, round(sh * price[(R, s)], 2)))

    nav = pd.DataFrame(nav_rows, columns=["strategy", "date", "nav", "cash", "invested"])
    return nav, pd.DataFrame(trade_rows, columns=["strategy", "date", "symbol", "side", "shares", "price", "cost"]), \
        pd.DataFrame(pos_rows, columns=["strategy", "date", "symbol", "shares", "value"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="momentum_delivery_lowvol")
    ap.add_argument("--start", default="2006-01-01")
    ap.add_argument("--capital", type=float, default=1_000_000)
    a = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print(f"Loading panel + prices for paper-trading '{a.strategy}' ...", flush=True)
    panel, rebals, gate = prepare(conn)
    ph = ",".join("?" * len(rebals))
    pr = pd.read_sql(f"SELECT date,symbol,close FROM stock_data_adj WHERE date IN ({ph})",
                     conn, params=rebals)
    price = {(d, s): c for d, s, c in zip(pr["date"], pr["symbol"], pr["close"])}

    nav, trades, pos = paper_trade(a.strategy, panel, rebals, gate, price, a.start, a.capital)

    for tbl, df in [("paper_nav", nav), ("paper_trades", trades), ("paper_positions", pos)]:
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        df.to_sql(tbl, conn, if_exists="replace", index=False)
    # live-vs-backtest drift: compare paper NAV returns to bt_portfolio_daily net_gated
    bt = pd.read_sql("SELECT date,net_gated FROM bt_portfolio_daily WHERE strategy=?",
                     conn, params=(a.strategy,))
    conn.commit(); conn.close()

    nav = nav.sort_values("date")
    nav["ret"] = nav["nav"].pct_change()        # return realized BY date R (from R-1 -> R)
    m = metrics(nav["ret"].dropna())
    # align: backtest net_gated[R] is the FORWARD return R->R+1, so the return realized
    # BY date R equals the backtest's net_gated at the PREVIOUS rebalance (shift +1).
    bt = bt.sort_values("date").reset_index(drop=True)
    bt["bt_realized_by"] = bt["net_gated"].shift(1)
    cmp = nav.merge(bt[["date", "bt_realized_by"]], on="date", how="inner")
    drift_corr = cmp["ret"].corr(cmp["bt_realized_by"])
    paper_cagr = (nav["nav"].iloc[-1] / a.capital) ** (12 / len(nav)) - 1

    print(f"\n=== PAPER-TRADING: {a.strategy}  ({nav['date'].iloc[0]} -> {nav['date'].iloc[-1]}) ===", flush=True)
    print(f"  start capital : Rs {a.capital:,.0f}", flush=True)
    print(f"  final NAV     : Rs {nav['nav'].iloc[-1]:,.0f}  ({nav['nav'].iloc[-1]/a.capital:.1f}x)", flush=True)
    print(f"  paper CAGR    : {paper_cagr*100:.1f}%   Sharpe {m['Sharpe']:.2f}   "
          f"MaxDD {m['MaxDD']*100:.1f}%   Calmar {m['Calmar']:.2f}", flush=True)
    print(f"  trades        : {len(trades):,}   total cost: Rs {trades['cost'].sum():,.0f} "
          f"({trades['cost'].sum()/a.capital*100:.0f}% of start capital over life)", flush=True)
    print(f"  LIVE vs BACKTEST drift: monthly-return corr = {drift_corr:.3f}  "
          f"(paper CAGR {paper_cagr*100:.1f}% vs backtest net) — high corr = engine faithful", flush=True)
    print(f"\n  Saved -> paper_nav / paper_positions / paper_trades.", flush=True)


if __name__ == "__main__":
    main()
