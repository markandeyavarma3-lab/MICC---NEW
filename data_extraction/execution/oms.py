#!/usr/bin/env python3
"""oms.py — PHASE 8: order-management + risk engine (PAPER-SAFE; live is gated).

The execution-stack skeleton for "trade-it-myself". Takes target weights, generates
orders vs current positions, runs every order through a RiskEngine (position cap,
liquidity/ADV limit, min-ticket), and routes accepted orders to a Broker. The only
wired broker is PaperBroker (simulated fills). LiveBroker is an explicit stub that
REFUSES to trade without API credentials + an explicit enable flag — no accidental
real orders. Writes `oms_orders`.

Run:  py -3.14 execution/oms.py                  # rebalance into today's signal portfolio (paper)
      py -3.14 execution/oms.py --capital 500000
"""
import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# risk limits
MAX_WEIGHT = 0.06          # max single-name target weight
MAX_ADV_PCT = 0.10         # an order may not exceed 10% of the name's daily turnover
MIN_TICKET = 5_000         # skip dust orders (Rs)
COST_SIDE = 0.0012


@dataclass
class Order:
    symbol: str
    side: str          # BUY / SELL
    qty: int
    price: float
    notional: float


@dataclass
class Fill:
    order: Order
    fill_price: float
    cost: float
    status: str        # FILLED / REJECTED
    reason: str = ""


class RiskEngine:
    def check(self, order, nav, adv):
        if order.notional < MIN_TICKET:
            return False, "below min ticket"
        if order.notional > MAX_WEIGHT * nav * 1.05:
            return False, f"exceeds {MAX_WEIGHT:.0%} position cap"
        if adv and order.notional > MAX_ADV_PCT * adv:
            return False, f"exceeds {MAX_ADV_PCT:.0%} of ADV (liquidity)"
        return True, ""


class Broker:
    def place(self, order):  # -> Fill
        raise NotImplementedError


class PaperBroker(Broker):
    """Simulated fills at price + half-spread slippage, with delivery costs."""
    def place(self, order):
        slip = 1 + (0.0005 if order.side == "BUY" else -0.0005)
        fp = order.price * slip
        return Fill(order, fp, order.notional * COST_SIDE, "FILLED")


class LiveBroker(Broker):
    """Real broker adapter — DISABLED. Requires API credentials + explicit enable."""
    def __init__(self, api_key=None, api_secret=None, enabled=False):
        self.enabled = enabled and api_key and api_secret

    def place(self, order):
        if not self.enabled:
            raise RuntimeError("LiveBroker disabled — set credentials + enabled=True to trade real money. "
                               "Build/verify on PaperBroker first.")
        raise NotImplementedError("Plug in Zerodha/Upstox REST here once paper-validated.")


class OMS:
    def __init__(self, broker, risk):
        self.broker, self.risk = broker, risk

    def rebalance(self, targets, prices, advs, positions, nav):
        """targets: {symbol: weight}. positions: {symbol: shares}. Returns list[Fill]."""
        fills = []
        names = set(targets) | set(positions)
        for sym in sorted(names):
            px = prices.get(sym)
            if not px or px <= 0:
                continue
            tgt_w = min(targets.get(sym, 0.0), MAX_WEIGHT)
            tgt_sh = int((nav * tgt_w) // px)
            d = tgt_sh - positions.get(sym, 0)
            if d == 0:
                continue
            order = Order(sym, "BUY" if d > 0 else "SELL", abs(d), px, abs(d) * px)
            ok, reason = self.risk.check(order, nav, advs.get(sym))
            if not ok:
                fills.append(Fill(order, px, 0.0, "REJECTED", reason))
                continue
            fills.append(self.broker.place(order))
        return fills


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=1_000_000)
    a = ap.parse_args()

    c = sqlite3.connect(DB_PATH, timeout=60)
    port = c.execute("SELECT symbol, score, med_turnover FROM current_signals "
                     "WHERE in_portfolio=1 ORDER BY rank").fetchall()
    asof = c.execute("SELECT MAX(rebal_date) FROM features_monthly").fetchone()[0]
    syms = [r[0] for r in port]
    advs = {r[0]: r[2] for r in port}
    px = dict(c.execute(
        f"SELECT symbol, close FROM stock_data_adj WHERE date=? AND symbol IN "
        f"({','.join('?'*len(syms))})", (asof, *syms)).fetchall()) if syms else {}
    targets = {s: 1.0 / len(syms) for s in syms} if syms else {}     # equal weight

    oms = OMS(PaperBroker(), RiskEngine())
    fills = oms.rebalance(targets, px, advs, positions={}, nav=a.capital)

    c.execute("""CREATE TABLE IF NOT EXISTS oms_orders (
        ts TEXT, asof TEXT, symbol TEXT, side TEXT, qty INTEGER, price REAL,
        notional REAL, status TEXT, reason TEXT)""")
    import datetime as _dt
    ts = _dt.datetime.now().isoformat()
    c.execute("DELETE FROM oms_orders WHERE asof=?", (asof,))
    c.executemany("INSERT INTO oms_orders VALUES (?,?,?,?,?,?,?,?,?)",
                  [(ts, asof, f.order.symbol, f.order.side, f.order.qty, round(f.fill_price, 2),
                    round(f.order.notional, 0), f.status, f.reason) for f in fills])
    c.commit()

    filled = [f for f in fills if f.status == "FILLED"]
    rej = [f for f in fills if f.status == "REJECTED"]
    deployed = sum(f.order.notional for f in filled)
    cost = sum(f.cost for f in filled)
    print("=" * 70)
    print(f"  OMS PAPER REBALANCE — target = today's signal portfolio (as-of {asof})")
    print(f"  capital Rs {a.capital:,.0f}  |  broker = PaperBroker (no real orders)")
    print("=" * 70)
    for f in filled[:12]:
        o = f.order
        print(f"  {o.side:4} {o.symbol:12} {o.qty:>6} @ {f.fill_price:>9.2f}  = Rs {o.notional:>11,.0f}")
    if len(filled) > 12:
        print(f"  ... +{len(filled)-12} more filled")
    for f in rej:
        print(f"  REJECT {f.order.symbol:12} {f.reason}")
    print("-" * 70)
    print(f"  {len(filled)} filled, {len(rej)} rejected | deployed Rs {deployed:,.0f} "
          f"({deployed/a.capital*100:.0f}%) | est cost Rs {cost:,.0f}")
    print(f"  Saved -> oms_orders.  LiveBroker is DISABLED (paper-safe).")
    c.close()


if __name__ == "__main__":
    main()
