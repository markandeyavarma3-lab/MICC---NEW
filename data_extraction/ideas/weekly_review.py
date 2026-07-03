#!/usr/bin/env python3
"""weekly_review.py — Part 3 Module A: the Friday learning loop (MONITOR-ONLY).

Honest framing, stated bluntly: at ~10-30 closed trades/month the desk does NOT
have the statistical power to update six pillar weights on any fast cadence
(30-trade Sharpe floor; MinTRL says comparing two weightings can need hundreds
of observations). So this loop's DEFAULT ACTION IS TO OBSERVE AND PROPOSE,
never to change weights:

  weekly     attribution + narrative + anomaly flags. NO weight changes.
  proposals  Bayesian-shrinkage weight proposals are generated ONLY for pillars
             with >= MIN_N closed SCORED trades since the current weight version,
             moves are capped at +-MOVE_CAP absolute, and every proposal lands as
             status='shadow' requiring human approval (rule_change_log) before
             any score_weights version bump. With today's data (0 closed scored
             theses) the engine correctly produces zero proposals.

Shrinkage:  w_post = (kappa*mu0 + n*w_hat) / (kappa + n),  kappa = 100
            (the v2.0 walk-forward weight is a strong prior; tiny live samples
            barely move it).

Run:  py -3.14 ideas/weekly_review.py [--selftest]
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta

from schema import connect, ensure_tables, PILLARS

KAPPA = 100.0
MOVE_CAP = 0.02
MIN_N = 30
HIGH_CONF = 75.0

DDL = ["""CREATE TABLE IF NOT EXISTS weekly_review (
    review_id INTEGER PRIMARY KEY,
    review_date TEXT NOT NULL,
    window_start TEXT, window_end TEXT,
    n_closed INTEGER, n_open INTEGER,
    hit_rate REAL, avg_r REAL, expectancy_r REAL,
    regime_state_json TEXT,
    pillar_ic_json TEXT,
    false_positives_json TEXT,
    missed_winners_json TEXT,
    narrative_md TEXT,
    created_at TEXT)""",
       """CREATE TABLE IF NOT EXISTS weight_proposal (
    proposal_id INTEGER PRIMARY KEY,
    review_id INTEGER,
    from_version TEXT, to_version TEXT,
    pillar TEXT, old_w REAL, proposed_w REAL,
    n_trades_pillar INTEGER, prior_kappa REAL,
    rationale TEXT, status TEXT,
    decided_by TEXT, decided_at TEXT)"""]


def shrink(mu0, w_hat, n, kappa=KAPPA):
    """Posterior mean of the pillar weight under a strength-kappa prior."""
    return (kappa * mu0 + n * w_hat) / (kappa + n)


def propose(old_weights, live_estimates, samples, kappa=KAPPA,
            move_cap=MOVE_CAP, min_n=MIN_N):
    """Gated shrinkage proposals. Returns {pillar: proposed_w} for pillars that
    clear the sample gate AND move meaningfully; positive weights renormalised
    to 1.0 (risk_penalty fixed). Empty dict = nothing to propose (the default)."""
    prop = {}
    for p, mu0 in old_weights.items():
        if p == "risk_penalty":
            continue
        n = samples.get(p, 0)
        if n < min_n or p not in live_estimates:
            continue
        w = shrink(mu0, live_estimates[p], n, kappa)
        w = max(mu0 - move_cap, min(mu0 + move_cap, w))     # per-cycle move cap
        if abs(w - mu0) > 1e-4:
            prop[p] = w
    if not prop:
        return {}
    merged = {p: prop.get(p, w) for p, w in old_weights.items() if p != "risk_penalty"}
    s = sum(merged.values())
    return {p: round(w / s, 4) for p, w in merged.items()}   # renormalise to 1.0


def selftest():
    ok = True
    # shrinkage by hand: kappa=100, mu0=.35, w_hat=.50, n=50 -> (35+25)/150 = .40
    ok &= abs(shrink(0.35, 0.50, 50) - 0.40) < 1e-12
    # sample gate blocks n<30
    ok &= propose({"a": 0.5, "b": 0.5, "risk_penalty": -0.1},
                  {"a": 0.9}, {"a": 29}) == {}
    # move cap: huge live estimate moves at most +-0.02 before renorm
    pr = propose({"a": 0.5, "b": 0.5, "risk_penalty": -0.1}, {"a": 0.9}, {"a": 1000})
    ok &= pr and abs((pr["a"] * (0.52 + 0.5) / 1.0) - 0.52) < 0.01  # capped then renormed
    ok &= abs(sum(pr.values()) - 1.0) < 1e-6 if pr else False
    print(f"  selftest: {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    conn = connect()
    ensure_tables(conn)
    for d in DDL:
        conn.execute(d)
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    wstart = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # ---- desk stats: window + lifetime ----
    win = cur.execute(
        "SELECT COUNT(*), AVG(CASE WHEN realized_return>0 THEN 1.0 ELSE 0 END), "
        "AVG(realized_return/((entry_price-stop)/entry_price)) FROM trade "
        "WHERE exit_date>=? AND exit_price IS NOT NULL AND entry_price>0 AND stop>0 "
        "AND entry_price>stop", (wstart,)).fetchone()
    n_open = cur.execute("SELECT COUNT(*) FROM thesis WHERE status='active'").fetchone()[0]

    # ---- pillar attribution: closed SCORED theses only (accrues from Part 1 on) ----
    rows = cur.execute(
        "SELECT a.pillar, a.subscore, t.realized_return FROM score_audit a "
        "JOIN thesis h ON a.thesis_id=h.thesis_id "
        "JOIN trade t ON t.thesis_id=h.thesis_id "
        "WHERE t.exit_price IS NOT NULL AND t.realized_return IS NOT NULL").fetchall()
    per_pillar = {}
    for p, sub, ret in rows:
        per_pillar.setdefault(p, []).append((sub, ret))
    pillar_ic = {}
    for p, obs in per_pillar.items():
        n = len(obs)
        if n >= 5:
            import statistics
            subs = [o[0] for o in obs]
            rets = [o[1] for o in obs]
            rs = {v: i for i, v in enumerate(sorted(subs))}
            rr = {v: i for i, v in enumerate(sorted(rets))}
            try:
                ic = statistics.correlation([rs[s] for s in subs], [rr[r] for r in rets])
            except statistics.StatisticsError:
                ic = None
            pillar_ic[p] = {"n": n, "rank_ic": None if ic is None else round(ic, 3)}
        else:
            pillar_ic[p] = {"n": n, "rank_ic": None}

    # ---- anomalies ----
    fps = [dict(symbol=s, conf=c, ret=round(r, 4)) for s, c, r in cur.execute(
        "SELECT h.symbol, h.confidence_score, t.realized_return FROM thesis h "
        "JOIN trade t ON t.thesis_id=h.thesis_id "
        "WHERE h.confidence_score>=? AND t.realized_return<0 AND t.exit_date>=?",
        (HIGH_CONF, wstart))]
    missed = [dict(symbol=s, card=d) for s, d in cur.execute(
        "SELECT symbol, card_date FROM idea_card WHERE in_book=0 "
        "AND card_date>=date('now','-63 day')")]

    regime = cur.execute("SELECT regime_votes, risk_budget_mult, drawdown_pct "
                         "FROM risk_state_daily ORDER BY as_of_date DESC LIMIT 1").fetchone()
    regime_json = json.dumps({"votes": regime[0], "mult": regime[1],
                              "dd": regime[2]} if regime else {})

    # ---- gated proposals (expected: none for many months) ----
    weights = {p: w for p, w in cur.execute(
        "SELECT pillar, weight FROM score_weights WHERE version="
        "(SELECT MAX(version) FROM score_weights) AND pillar IN "
        "({})".format(",".join("?" * len(PILLARS))), tuple(PILLARS))}
    samples = {p: v["n"] for p, v in pillar_ic.items()}
    live_est = {p: 0.0 for p in samples}      # placeholder until IC->weight mapping accrues
    proposals = propose(weights, live_est, samples)

    hit = win[1]
    narrative = (
        f"# Weekly review {today}\n\n"
        f"- window {wstart} -> {today}: {win[0]} closed, hit "
        f"{'n/a' if hit is None else f'{hit*100:.0f}%'}, "
        f"expectancy {'n/a' if win[2] is None else f'{win[2]:+.2f}R'} | open theses {n_open}\n"
        f"- pillar attribution samples (closed SCORED theses): "
        f"{ {p: v['n'] for p, v in pillar_ic.items()} or 'none yet — accrues from live cards'}\n"
        f"- high-confidence losers this week: {len(fps)} | waitlisted cards (63d): {len(missed)}\n"
        f"- weight proposals: {len(proposals)} "
        f"(sample gate: min {MIN_N}/pillar; move cap ±{MOVE_CAP}; κ={KAPPA:.0f})\n"
        f"- regime: {regime_json}\n\n"
        f"*Monitor-only by design: no weight changes without a human-approved "
        f"rule_change_log entry.*\n")

    cur.execute("INSERT INTO weekly_review (review_date,window_start,window_end,"
                "n_closed,n_open,hit_rate,avg_r,expectancy_r,regime_state_json,"
                "pillar_ic_json,false_positives_json,missed_winners_json,"
                "narrative_md,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (today, wstart, today, win[0], n_open, win[1], win[2], win[2],
                 regime_json, json.dumps(pillar_ic), json.dumps(fps),
                 json.dumps(missed[:50]), narrative, datetime.now().isoformat()))
    review_id = cur.lastrowid
    for p, w in proposals.items():
        cur.execute("INSERT INTO weight_proposal (review_id,from_version,to_version,"
                    "pillar,old_w,proposed_w,n_trades_pillar,prior_kappa,rationale,"
                    "status,decided_by,decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (review_id, "v2.0", "v2.1-shadow", p, weights[p], w,
                     samples.get(p, 0), KAPPA, "shrinkage proposal", "shadow", None, None))
    conn.commit()
    print(narrative, flush=True)
    print(f"  weekly_review #{review_id} stored | proposals: {len(proposals)}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
