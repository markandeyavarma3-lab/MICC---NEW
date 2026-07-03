#!/usr/bin/env python3
"""preregister_signals.py — Part 2 governance: pre-registered validation windows,
pass thresholds and kill criteria for every signal that wants scoring weight.

THE RULE: nothing may hold evidence_tier='scored' (or a score_weights pillar
backed by it) without a row here whose thresholds its validation results satisfy.
Anything not pre-registered stays a context tag. This file is the registry's only
writer — amendments happen HERE, in git, never ad-hoc in the DB. That closes the
door on quiet post-hoc promotion.

verify_phases (P14) enforces: scored => prereg row exists AND registered
thresholds are actually met by the persisted validation results.

Idempotent. Run:  py -3.14 common/preregister_signals.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")

DDL = """CREATE TABLE IF NOT EXISTS signal_preregistration (
    signal TEXT PRIMARY KEY,
    test TEXT,               -- what is measured
    window TEXT,             -- data window the test runs on
    pass_threshold TEXT,     -- machine-checkable rule to EARN 'scored'
    kill_criteria TEXT,      -- rule that DEMOTES it on weekly revalidation
    status TEXT,             -- scored | context | pending_depth | killed
    registered_at TEXT,
    notes TEXT
)"""

# (signal, test, window, pass_threshold, kill_criteria, status, notes)
REGISTRY = [
    ("insider_cluster_buy",
     "21d NIFTY-adjusted AR event study; entry first close AFTER filing",
     "2016->present, expanding; weekly revalidation",
     "mean>0 AND t>=3.0 AND H2>0",
     "demote to context if any of: mean<=0, t<3.0, H2<=0 on revalidation",
     "scored", "passed 2026-07: +2.97%, t=3.67, H2 +5.67%"),
    ("regime_spine",
     "WF-gated OOS Sharpe vs incumbent 4-vote gate, IV book, identical months",
     "2009->present, 48mo min train; weekly revalidation",
     "sharpe_spine > sharpe_incumbent",
     "stays context while it does not beat the incumbent",
     "context", "failed 2026-07: 1.42 vs 1.53 -> NO-SHIP"),
    ("amihud",
     "monthly cross-sectional rank-IC vs fwd_ret_1m, top-500 liquid",
     "2005->present; weekly revalidation",
     "mean IC>0 AND t>=3.0 AND H2>0",
     "stays context; NEVER scored with negative IC",
     "context", "failed 2026-07: IC -0.020 (wrong sign in liquidity-filtered universe)"),
    ("rs_sector_6m",
     "monthly cross-sectional rank-IC vs fwd_ret_1m, top-500 liquid",
     "2005->present; weekly revalidation",
     "mean IC>0 AND t>=3.0 AND H2>0",
     "stays context below threshold",
     "context", "failed 2026-07: IC +0.013, t=1.37, decaying"),
    ("pead_proxy",
     "true Foster SUE + 60d drift event study (needs >=12 PIT quarters/symbol)",
     "activates when fundamentals_pit depth >= 12 quarters (est. 2028, sooner if backfilled)",
     "P10-P1 drift spread > 0 AND t>=3.0 AND H2>0",
     "context until depth gate met; never scored on the YoY proxy",
     "pending_depth", "local depth ~5.5 quarters (2024->2026)"),
    ("buyback_announce",
     "post-announcement residual drift event study",
     "activates at >=100 local announcement events with PIT dates",
     "mean>0 AND t>=3.0 AND H2>0",
     "context until event-count gate met",
     "pending_depth", "20 local events (announcements table spans ~1 month)"),
    ("index_inclusion",
     "announcement->effective window study (needs ANNOUNCEMENT dates, not just effective months)",
     "blocked on an announcement-dated source",
     "mean>0 AND t>=3.0 AND H2>0 over the announcement window",
     "context; niftyindices gives effective months only",
     "context", "58 effective-month events; announcement dates unavailable free"),
    ("sector_align",
     "stock-level rs_sector_6m IC is the gate for any sector pillar weight",
     "same as rs_sector_6m",
     "rs_sector_6m must pass its own gate first",
     "sector engine stays context/display while rs_sector fails",
     "context", "doc prior 0.02 weight NOT granted"),
    ("fno_positioning",
     "PCR / max-pain / OI-buildup / FII futures long-short as stock-level signals",
     "n/a",
     "would require a new pre-registration with a walk-forward event study",
     "killed: no rigorous India OOS evidence; coincident sentiment only",
     "killed", "participant OI feeds the context-tier spine flow_axis only"),
    ("calendar_seasonality",
     "Diwali / month-of-year directional effects",
     "n/a",
     "would require a new pre-registration",
     "killed: not statistically significant in Indian studies",
     "killed", "budget/results windows remain calendar-awareness gates, not signals"),
]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute(DDL)
    from datetime import datetime
    now = datetime.now().isoformat()
    for sig, test, window, pas, kill, status, notes in REGISTRY:
        # keep original registered_at on re-runs (idempotent, append-only semantics)
        old = conn.execute("SELECT registered_at FROM signal_preregistration WHERE signal=?",
                           (sig,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO signal_preregistration VALUES (?,?,?,?,?,?,?,?)",
                     (sig, test, window, pas, kill, status, old[0] if old else now, notes))
    conn.commit()
    for r in conn.execute("SELECT signal, status FROM signal_preregistration ORDER BY signal"):
        print(f"  {r[0]:22} {r[1]}", flush=True)
    n = conn.execute("SELECT COUNT(*) FROM signal_preregistration").fetchone()[0]
    print(f"  {n} signals pre-registered", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
