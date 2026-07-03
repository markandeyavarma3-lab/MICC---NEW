#!/usr/bin/env python3
"""scoring.py — Stage 4: transparent, versioned, auditable linear confidence scorer.

confidence = clamp( Sum_pillar (weight_pillar * subscore_pillar), 0, 100 )
then a fundamentals cap for value/quality theses (A3).

Every score is fully reproducible: the six per-pillar (subscore, weight,
contribution) rows are persisted to score_audit, and weights live in the versioned
score_weights table (never hard-coded into the number). This is the exact analog of
a SHAP breakdown, but exact because the model is linear. The Friday learning loop
(Part 3) proposes new weight *versions*; it never edits code.

Pillars (0..100 each): signal_strength, trend_align, regime_align,
liquidity_capacity, confirmation, risk_penalty (risk_penalty is negative-weighted).

Run:  py -3.14 ideas/scoring.py
"""
from schema import connect, ensure_tables, PILLARS

WEIGHT_VERSION = "v2.0"

# risk_penalty MUST be <= 0; positive pillars MUST sum to 1.0 (asserted in seed).
WEIGHTS = {
    "signal_strength":    0.35,
    "trend_align":        0.18,
    "regime_align":       0.15,
    "confirmation":       0.12,
    "liquidity_capacity": 0.10,
    "event_score":        0.10,
    "risk_penalty":      -0.10,
}
RATIONALE = {
    "signal_strength":    "primary momentum composite (generate_signals) — dominant driver",
    "trend_align":        "single-stock trend: ADX-14 + distance above 200DMA",
    "regime_align":       "VALIDATED 4-vote macro gate (breadth/NIFTY/SPX/VIX), as-of; "
                          "replaces raw breadth (double-count fix); spine NO-SHIP (1.42<1.53)",
    "confirmation":       "delivery% confirmation of the move",
    "liquidity_capacity": "median-turnover percentile within the book",
    "event_score":        "scored events only: insider cluster buys (event study t=3.67, "
                          "+2.97% 21d AR); recency-decayed. PEAD/buyback/inclusion = context",
    "risk_penalty":       "ATR-14 volatility drag + active promoter-pledge flag (negative weight)",
}
# A3 fundamentals cap: value/quality theses cannot exceed this confidence until the
# symbol has >= FUND_MIN_YEARS of annual fundamentals. Data ceiling today is ~5yr.
FUND_CAP = 70.0
FUND_MIN_YEARS = 8
FUND_CAP_RATIONALE = (f"A3: value/quality theses clamped to <= {FUND_CAP:.0f} until "
                      f">= {FUND_MIN_YEARS}yr annual coverage (current depth ~5yr)")


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def seed_weights(conn, version=WEIGHT_VERSION, weights=None):
    weights = weights or WEIGHTS
    pos = sum(w for p, w in weights.items() if w > 0)
    assert abs(pos - 1.0) < 1e-9, f"positive weights must sum to 1.0, got {pos}"
    assert weights["risk_penalty"] <= 0, "risk_penalty weight must be <= 0"
    import datetime
    today = datetime.date.today().isoformat()
    for p in PILLARS:
        conn.execute("INSERT OR REPLACE INTO score_weights VALUES (?,?,?,?,?)",
                     (version, p, weights[p], today, RATIONALE[p]))
    # store the cap as an auditable meta-row (pillar='_fund_cap')
    conn.execute("INSERT OR REPLACE INTO score_weights VALUES (?,?,?,?,?)",
                 (version, "_fund_cap", FUND_CAP, today, FUND_CAP_RATIONALE))
    conn.commit()


def load_weights(conn, version=WEIGHT_VERSION):
    return {p: w for p, w in conn.execute(
        "SELECT pillar,weight FROM score_weights WHERE version=? AND pillar IN "
        "({})".format(",".join("?" * len(PILLARS))), (version, *PILLARS))}


def annual_years(conn, symbol):
    """Fundamentals depth for the A3 cap. Base = yfinance annual_income years.
    The deeper screener history (fundamentals_depth) counts ONLY if the
    '_cap_lift_enabled' switch was human-approved after a value re-backtest pass
    — which it was NOT (2026-07 re-backtest FAILED: value/quality ICs ~0 even
    with survivor tailwind), so this stays on the conservative base."""
    r = conn.execute("SELECT COUNT(DISTINCT substr(report_date,1,4)) FROM annual_income "
                     "WHERE symbol=?", (symbol,)).fetchone()
    base = r[0] if r else 0
    try:
        lift = conn.execute("SELECT COUNT(*) FROM score_weights "
                            "WHERE pillar='_cap_lift_enabled'").fetchone()[0]
        if lift:
            d = conn.execute("SELECT depth_years FROM fundamentals_depth "
                             "WHERE symbol=? AND validated=1", (symbol,)).fetchone()
            if d:
                return max(base, d[0])
    except Exception:
        pass
    return base


def apply_fundamentals_cap(thesis_type, years, conf):
    """A3: clamp value/quality confidence until fundamentals depth is sufficient."""
    if thesis_type in ("value", "quality") and years < FUND_MIN_YEARS:
        return min(conf, FUND_CAP)
    return conf


def regime_votes(conn, card_date):
    """The VALIDATED 4-vote macro gate, as-of card_date (trailing only):
    breadth>=50, NIFTY>200DMA, SPX>200DMA, IndiaVIX<1yr median. Returns 0..4."""
    votes = 0
    br = conn.execute("SELECT pct_above_200dma FROM market_breadth WHERE date<=? "
                      "ORDER BY date DESC LIMIT 1", (card_date,)).fetchone()
    votes += 1 if br and br[0] is not None and br[0] >= 50 else 0
    for sym, kind in [("NIFTY50", "trend"), ("SPX", "trend"), ("IndiaVIX", "vix")]:
        rows = conn.execute("SELECT close FROM global_indices_daily WHERE symbol=? "
                            "AND date<=? ORDER BY date DESC LIMIT 252",
                            (sym, card_date)).fetchall()
        if len(rows) < 200:
            continue
        closes = [r[0] for r in rows]           # newest first
        if kind == "trend":
            votes += 1 if closes[0] > sum(closes[:200]) / 200 else 0
        else:
            med = sorted(closes)[len(closes) // 2]
            votes += 1 if closes[0] < med else 0
    return votes


def event_subscores(conn, card_date, symbols):
    """Per-symbol event pillar (0..100, 50 = neutral) from SCORED events only,
    linearly recency-decayed over each event's decay horizon. Plus the active
    promoter-pledge risk flag for the risk_penalty pillar."""
    import datetime as _dt
    d0 = _dt.date.fromisoformat(card_date)
    ev, pledge = {}, set()
    qmarks = ",".join("?" * len(symbols))
    # STRICT '<': an event filed ON card_date cannot influence that date's score
    # (EOD system — the card is built at that close; same-day info is a PIT leak)
    for sym, ed, etype, direction, horizon, tier in conn.execute(
            f"SELECT symbol,event_date,event_type,direction,decay_horizon_days,evidence_tier "
            f"FROM event_signals WHERE symbol IN ({qmarks}) AND event_date<? "
            f"AND evidence_tier IN ('scored','risk')", (*symbols, card_date)):
        age = (d0 - _dt.date.fromisoformat(ed)).days
        if age > (horizon or 63):
            continue
        if tier == "risk":
            pledge.add(sym)
            continue
        fresh = 1 - age / (horizon or 63)       # 1 at event, 0 at horizon
        boost = 50 * fresh * (1 if direction == "bullish" else -1)
        ev[sym] = clamp(50 + max(ev.get(sym, 50) - 50, boost))  # strongest active event
    return ev, pledge


def compute_subscores(conn, card_date, symbols):
    """Return {symbol: {pillar: subscore}} for the given book on card_date."""
    regime_align = regime_votes(conn, card_date) / 4 * 100
    ev, pledged = event_subscores(conn, card_date, symbols)

    sig = {r[0]: r for r in conn.execute(
        "SELECT symbol,score,deliv_1m,med_turnover FROM current_signals "
        "WHERE rebal_date=?", (card_date,))}
    tech = {r[0]: r for r in conn.execute(
        "SELECT symbol,adx_14,pct_above_sma200,atr_14_pct FROM symbol_technicals")}

    # liquidity percentile within the book
    turns = sorted(sig[s][3] for s in symbols if s in sig and sig[s][3] is not None)
    def pct_rank(v):
        if not turns or v is None:
            return 50.0
        import bisect
        return 100.0 * bisect.bisect_right(turns, v) / len(turns)

    out = {}
    for s in symbols:
        srow = sig.get(s); trow = tech.get(s)
        score = srow[1] if srow else 50.0
        deliv = srow[2] if srow and srow[2] is not None else 50.0
        turn  = srow[3] if srow else None
        adx   = trow[1] if trow and trow[1] is not None else 0.0
        above = trow[2] if trow and trow[2] is not None else 0.0
        atr   = trow[3] if trow and trow[3] is not None else 0.0
        out[s] = {
            "signal_strength":    clamp(score),
            "trend_align":        0.5 * clamp(50 + above) + 0.5 * clamp(adx * 2),
            "regime_align":       regime_align,
            "confirmation":       clamp(deliv),
            "liquidity_capacity": pct_rank(turn),
            "event_score":        ev.get(s, 50.0),          # 50 = no active scored event
            "risk_penalty":       clamp(atr * 10 + (25 if s in pledged else 0)),
        }
    return out


def composite(subscores, weights):
    return sum(weights[p] * subscores[p] for p in PILLARS)


def score_thesis(conn, thesis_id, card_date, symbol, thesis_type, subscores,
                 weights, version=WEIGHT_VERSION):
    raw = composite(subscores, weights)
    conf = clamp(raw)
    conf = apply_fundamentals_cap(thesis_type, annual_years(conn, symbol), conf)
    conn.execute("DELETE FROM score_audit WHERE thesis_id=? AND card_date=?",
                 (thesis_id, card_date))
    for p in PILLARS:
        contrib = weights[p] * subscores[p]
        conn.execute("INSERT INTO score_audit VALUES (?,?,?,?,?,?,?)",
                     (thesis_id, card_date, p, subscores[p], weights[p], contrib, version))
    conn.execute("UPDATE thesis SET confidence_score=?, weight_version=? WHERE thesis_id=?",
                 (round(conf, 2), version, thesis_id))
    return conf


def main():
    conn = connect()
    ensure_tables(conn)
    seed_weights(conn)
    weights = load_weights(conn)

    card_date = conn.execute("SELECT MAX(rebal_date) FROM current_signals").fetchone()[0]
    live = conn.execute(
        "SELECT thesis_id,symbol,thesis_type FROM thesis "
        "WHERE narrative='live:momentum_bands' AND created_at=?", (card_date,)).fetchall()
    symbols = [s for _, s, _ in live]
    subs = compute_subscores(conn, card_date, symbols)

    for tid, sym, ttype in live:
        score_thesis(conn, tid, card_date, sym, ttype, subs[sym], weights)
    conn.commit()

    # --- self-checks ---
    n = len(live)
    # reproducibility: recompute confidence from score_audit == stored
    mismatches = 0
    for tid, sym, ttype in live:
        raw = conn.execute("SELECT SUM(contribution) FROM score_audit "
                           "WHERE thesis_id=? AND card_date=?", (tid, card_date)).fetchone()[0]
        recomputed = apply_fundamentals_cap(ttype, annual_years(conn, sym), clamp(raw))
        stored = conn.execute("SELECT confidence_score FROM thesis WHERE thesis_id=?",
                             (tid,)).fetchone()[0]
        if abs(round(recomputed, 2) - stored) > 0.01:
            mismatches += 1
    rng = conn.execute("SELECT MIN(confidence_score),AVG(confidence_score),"
                      "MAX(confidence_score) FROM thesis WHERE narrative='live:momentum_bands' "
                      "AND created_at=?", (card_date,)).fetchone()
    print(f"  scored {n} live theses (weights {WEIGHT_VERSION})", flush=True)
    print(f"  confidence min/avg/max = {rng[0]:.1f}/{rng[1]:.1f}/{rng[2]:.1f}", flush=True)
    print(f"  {'PASS' if mismatches == 0 else 'FAIL'}: confidence reproducible from "
          f"score_audit ({n-mismatches}/{n})", flush=True)
    # A3 sanity: a synthetic value thesis on a <8yr symbol is capped
    demo_sym = conn.execute("SELECT symbol FROM annual_income GROUP BY symbol "
                           "HAVING COUNT(DISTINCT substr(report_date,1,4))<8 LIMIT 1").fetchone()[0]
    capped = apply_fundamentals_cap("value", annual_years(conn, demo_sym), 95.0)
    print(f"  {'PASS' if capped <= FUND_CAP else 'FAIL'}: A3 value cap "
          f"({demo_sym} 95->{capped})", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
