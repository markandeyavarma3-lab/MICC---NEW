#!/usr/bin/env python3
"""build_bands.py — Stage 3: turn the live top-decile book into idea theses with
ATR-based entry/stop/target bands, an auto-assigned swing/positional timeframe,
and equal-risk integer sizing.

Supersedes the old fixed-sigma / hard-1-month band logic in
common/recommendations.py. Reads the current book (current_signals, in_portfolio)
and daily ATR (symbol_technicals.atr_14_pct, in PERCENT). The ATR multiplier `k`
is persisted per trade (trade.atr_k) so Part 3 can re-calibrate.

Bands:
  timeframe = positional  if strong trend (adx_14 >= ADX_TREND and above 200DMA)
              swing        otherwise
  k         = K_SWING | K_POSITIONAL          (conventional, re-calibrate later)
  stop      = entry * (1 - k * atr_frac)
  target    = entry * (1 + R * k * atr_frac)  -> reward:risk = R:1
  size      = floor(RISK_BUDGET / (entry - stop))   (equal rupee risk per idea)

Idempotent: replaces the live band theses for the current card_date only.
Run:  py -3.14 ideas/build_bands.py
"""
import math
import os

from schema import connect, ensure_tables

LIVE_TAG   = "live:momentum_bands"
# --- capital & risk config (env-overridable; defaults = owner's stated book) ---
CAPITAL     = float(os.environ.get("MICC_CAPITAL", "10000000"))   # INR 1 crore
RISK_BUDGET = float(os.environ.get("MICC_RISK_BUDGET", "10000"))  # INR risk per idea
MAX_STOP_PCT     = 0.10   # owner rule: stop is NEVER more than 10% below entry
MAX_POSITION_PCT = 0.10   # single position notional <= 10% of capital (concentration cap)
ADX_TREND  = 25.0        # ADX above this = trending -> positional
K_SWING       = 1.75     # ATR multiplier, swing (placeholder; re-calibrated in Part 3)
K_POSITIONAL  = 2.75     # ATR multiplier, positional (placeholder; re-calibrated in Part 3)
R_MULTIPLE = 2.0         # target distance = R x stop distance (1:2 reward:risk)
MAX_ATR_FRAC = 0.9       # guard: skip pathological ATR that would push stop<=0


def classify(adx, above_200):
    strong = (adx is not None and adx >= ADX_TREND) and bool(above_200)
    return ("positional", K_POSITIONAL) if strong else ("swing", K_SWING)


def main():
    conn = connect()
    ensure_tables(conn)
    cur = conn.cursor()

    card_date = cur.execute("SELECT MAX(rebal_date) FROM current_signals").fetchone()[0]
    book = cur.execute(
        "SELECT cs.symbol, cs.company, cs.score, st.atr_14_pct, st.adx_14, "
        "st.pct_above_sma200 "
        "FROM current_signals cs JOIN symbol_technicals st ON cs.symbol=st.symbol "
        "WHERE cs.rebal_date=? AND cs.in_portfolio=1 AND st.atr_14_pct IS NOT NULL",
        (card_date,)).fetchall()

    # --- idempotent reset of this date's live band theses ---
    old = [r[0] for r in cur.execute(
        "SELECT thesis_id FROM thesis WHERE narrative=? AND created_at=?",
        (LIVE_TAG, card_date))]
    if old:
        qm = ",".join("?" * len(old))
        cur.execute(f"DELETE FROM trade WHERE thesis_id IN ({qm})", old)
        cur.execute(f"DELETE FROM thesis WHERE thesis_id IN ({qm})", old)
        conn.commit()

    made = skipped = 0
    for symbol, company, score, atr_pct, adx, above_pct in book:
        atr_frac = (atr_pct or 0) / 100.0            # percent -> fraction
        if atr_frac <= 0 or atr_frac >= MAX_ATR_FRAC:
            skipped += 1
            continue
        entry = cur.execute(
            "SELECT close FROM stock_data_adj WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,)).fetchone()
        if not entry or not entry[0] or entry[0] <= 0:
            skipped += 1
            continue
        entry = float(entry[0])
        tf, k = classify(adx, (above_pct or 0) > 0)
        # ATR-derived stop distance, but never wider than MAX_STOP_PCT (owner rule)
        stop_dist = min(entry * k * atr_frac, entry * MAX_STOP_PCT)
        stop = round(entry - stop_dist, 2)
        stop_dist = entry - stop                      # rounded distance drives all downstream
        if stop_dist <= 0:
            skipped += 1
            continue
        target = round(entry + R_MULTIPLE * stop_dist, 2)
        size = int(math.floor(RISK_BUDGET / stop_dist))
        # concentration cap: a single position can't exceed MAX_POSITION_PCT of capital
        size = min(size, int(math.floor(MAX_POSITION_PCT * CAPITAL / entry)))
        if size < 1 or not (stop < entry < target):
            skipped += 1
            continue

        cur.execute(
            "INSERT INTO thesis (created_at,symbol,thesis_type,source_signal,"
            "timeframe_class,regime_at_creation,confidence_score,weight_version,"
            "narrative,status,invalidation_condition,closed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (card_date, symbol, "momentum", "momentum_delivery_lowvol", tf, None,
             score, None, LIVE_TAG, "active",
             f"close below stop {stop}", None))
        tid = cur.lastrowid
        cur.execute(
            "INSERT INTO trade (thesis_id,entry_date,entry_price,stop,target,"
            "size_shares,atr_k,exit_date,exit_price,exit_reason,realized_return) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tid, card_date, entry, stop, target, size, k, None, None, None, None))
        made += 1

    conn.commit()

    # --- self-check invariants (mirror verify_phases) ---
    rows = cur.execute(
        "SELECT t.entry_price,t.stop,t.target,t.size_shares,t.atr_k "
        "FROM trade t JOIN thesis h ON t.thesis_id=h.thesis_id "
        "WHERE h.narrative=? AND h.created_at=?", (LIVE_TAG, card_date)).fetchall()
    ok_order = all(s < e < tg for e, s, tg, _, _ in rows)
    ok_size  = all(sz >= 1 for _, _, _, sz, _ in rows)
    # owner rule: stop never more than 10% below entry
    ok_stop = all((e - s) <= MAX_STOP_PCT * e + 0.01 for e, s, tg, sz, _ in rows)
    # risk never EXCEEDS the per-idea budget (position cap can only lower it)
    ok_risk = all(sz * (e - s) <= RISK_BUDGET + (e - s) + 1e-6 for e, s, tg, sz, _ in rows)
    # no single position exceeds the concentration cap
    ok_conc = all(sz * e <= MAX_POSITION_PCT * CAPITAL + e + 1e-6 for e, s, tg, sz, _ in rows)
    tf_counts = {}
    for r in cur.execute("SELECT timeframe_class,COUNT(*) FROM thesis WHERE narrative=? "
                         "AND created_at=? GROUP BY timeframe_class", (LIVE_TAG, card_date)):
        tf_counts[r[0]] = r[1]
    print(f"  card_date={card_date}  made={made} skipped={skipped}", flush=True)
    print(f"  timeframe split: {tf_counts}", flush=True)
    print(f"  {'PASS' if ok_order else 'FAIL'}: stop<entry<target for all", flush=True)
    print(f"  {'PASS' if ok_size else 'FAIL'}: size>=1 for all", flush=True)
    print(f"  {'PASS' if ok_stop else 'FAIL'}: stop-loss <= {MAX_STOP_PCT:.0%} for all", flush=True)
    print(f"  {'PASS' if ok_risk else 'FAIL'}: risk <= budget per idea", flush=True)
    print(f"  {'PASS' if ok_conc else 'FAIL'}: position <= {MAX_POSITION_PCT:.0%} of capital", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
