# MICC — Part 3: Learning Loop, Risk Engine, Calibration, Fundamentals & ML Harness (As-Built)

**Status:** ✅ Core modules built · `verify_phases.py` **98/98 green** (79 after Part 2 review)
**Date:** 2026-07 · **DB:** `D:\MICC\marketDB\db\market.db` · **Interpreter:** `py -3.14`

Part 3's premise, stated bluntly (and enforced in code): **at ~10–30 closed trades a
month the desk does not have the statistical power to update six pillar weights on a
fast cadence.** So everything self-modifying is monitor-only, sample-gated, shadowed,
and human-approved. Everything new is a challenger; the linear composite is champion.

---

## 1. Verdict scoreboard (what our own data said)

| Study | Pre-registered gate | Result | Verdict |
|---|---|---|---|
| **Exit variants** (6 tested on the OHLC paths of 540 closed trades) | beat current ExpR on train AND held-out 30% AND MFE capture ≥ 0.60 | widening stops degrades test ExpR monotonically (−0.018→−0.045); whipsaw **falsified**: only **1%** of stops later hit target; `trail_atr3` near-miss (best test ExpR +0.030, MFEcap 0.58) | **KEEP current bands** |
| **Ridge challenger** (CPCV 15 paths) | median path Sharpe > champion AND DSR>0.5 AND stability | 0.61 vs champion **1.00** | **KILLED** |
| **LightGBM challenger** (CPCV 15 paths) | same | 0.80 vs **1.00** (DSR 0.92, Kendall W 0.84 — but must beat champion) | **KILLED** |
| **Weight proposals** (first Friday review) | ≥30 closed *scored* trades per pillar | 0 scored-closed samples | **0 proposals** (gates hold) |

The champion linear composite survived every challenger again — now under CPCV +
deflated-Sharpe rigor rather than a single split.

## 2. Modules as built

**C — Exit calibration** (`common/calibrate_exits.py`): MFE/MAE study, EOD-honest
simulation (entry bar after signal; same-day stop-before-target). Verdicts in
`exit_calibration`; any future ADOPT requires human approval via `rule_change_log`.
Quarterly re-run is the cadence (wire when desired).

**B — Risk meta-engine** (`common/build_risk_state.py`, daily phase `risk_state`):
R-based desk equity curve → `risk_state_daily`. DD brake ×1.0/0.75/0.5/0.25 at
10/15/22% (halt >22%), 3-loss streak brake ×0.75, combined = min (never >1), regime
throttle, sector concentration + 60d pairwise corr (>0.6 throttles). Wired:
`build_bands` scales `RISK_BUDGET` by the mult; halt sends all new cards to waitlist.
`--selftest` covers every threshold. Governance, **not** alpha — stated in-code.
Confidence-scaled sizing deliberately NOT enabled. Current: +₹467k cum R-pnl, DD 3.9%.

**F(c) — Backups/ops** (`automation/backup_db.py`, weekly phase `db_backup`):
`VACUUM INTO` dated backup → `integrity_check` on the backup → WAL checkpoint →
retention (2 weekly + 2 monthly-firsts). First backup: 18.7 GB in 6.3 min, ic=ok.
`--drill` restore drill **PASS** (integrity + key-table counts vs live).

**A — Friday learning loop, monitor-only** (`ideas/weekly_review.py`, weekly phase):
weekly attribution (window stats, per-pillar rank-IC from `score_audit`×outcomes,
high-confidence losers, waitlist log), narrative markdown, and a **gated Bayesian
proposal engine**: `w_post = (κ·μ₀ + n·ŵ)/(κ+n)` with κ=100, move cap ±0.02,
min-n 30/pillar, renormalise-to-1, status='shadow', human approval required.
`--selftest` proves the math/gates by hand. First review: 11 closed this week,
73% hit, +0.54R, **0 proposals**.

**D(b) — Fundamentals PIT integration** (`events/integrate_screener_pit.py`, weekly
phase `screener_pit`): scrape completed (494/494 fetched, 440 parsed). PIT convention:
`pit_date = FY-end + 60d`, every row `pit_estimated=1`. Validation vs yfinance
overlap (Net Profit within 25%): **397/411 validated**; `fundamentals_depth` →
**356 symbols cap-lift-eligible** (≥8yr AND validated). **The cap-lift switch is OFF**
— value/quality stay clamped ≤70 until a value re-backtest on the extended history
clears its pre-registered bar and a human approves (`_cap_lift_enabled` + P18 check).

**D(a) — Event shadow log** (`ideas/event_shadow.py`, daily phase `event_shadow`):
2,023 would-be event ideas (2024→), entries strictly after event date, forward
returns filled at 21/63/126td. Promotion needs ≥12 months AND ≥30 filled instances
AND beats the momentum baseline — none eligible yet. Early raw reads: pead_proxy
avg63 +3.6% (347 filled), insider +1.5% (406) — unadjusted, scoreboard only.

**E — ML/CPCV harness** (`common/ml_cpcv_harness.py`, run quarterly by hand):
CPCV(6,2)=15 purged+embargoed paths on 109k panel rows; ridge + LightGBM vs the
frozen champion composite; pooled deflated Sharpe; LightGBM importance stability
(Kendall W). Experiments + per-path results persisted (`ml_experiment`,`ml_result`)
with pre-registered criteria attached. Deploy scope if ever passed: **re-rank within
the linear top-N only** — never overrides gates or caps.

## 3. Bug found by the suite en route
The daily `build_event_signals` rebuild was resetting the insider tier to 'context',
clobbering the event-study verdict between weekly re-runs. Fixed: the builder now
reads the persisted `event_validation` verdict at build time — a rebuild can never
silently demote (or promote) a signal.

## 4. Verification — 79 → 98 checks
P15 exit-calibration honesty · P16 risk-engine threshold re-derivations + halt
enforcement · P17 loop isolation (move cap, sample gate, no unapproved weight
version) · P18 PIT lag/flags, cap-lift eligibility re-derivation, switch-off ·
P19 ML statuses, killed-challenger record, shadow entry/PIT and isolation.

## 5. Remaining Part 3 items (honest list)
- ~~Value/quality re-backtest~~ **DONE 2026-07-03: FAIL.** 131 months (2015→2026):
  value_ep IC +0.005 (t=0.48), quality_margin −0.003, quality_growth +0.001 — zero
  predictive power even with the survivor tailwind. **Cap stays, now evidence-backed.**
  Re-runs weekly (`value_gate`) as PIT depth grows; `--approve-cap-lift` exists but
  requires a scored verdict it does not have.
- ~~Quarterly cadences~~ **DONE**: `exit_recal` + `ml_gate` weekly phases with --auto
  80-day self-gates.
- **Event promotion** decision point arrives ~mid-2027 (12 months of shadow).
- ~~Delivery polish~~ **DONE**: ntfy failure alerts (topic in `MICC_NTFY_TOPIC`),
  dashboard risk-state/weekly-review/context/weight-evolution panels.
- **Live capital**: gated on 12–18 months of paper Idea-Engine track record with
  hit-rate ≥49%, positive MinTRL-informed Sharpe, DD within −30%. Kite order APIs are
  free (data ₹500/mo); static-IP requirement applies from 2026-04-01. **Not now.**

## 6. What MICC now is / is not
**Is:** a single-edge (momentum_delivery_lowvol), long-only, EOD Indian-equity idea
desk with validated regime gating, evidence-graded events, portfolio risk governance,
self-monitoring learning scaffolding, integrity-checked backups, and a disciplined
challenger harness — fully versioned, explainable, reproducible, 98-check verified.
**Is not:** a multi-strategy alpha factory, an intraday system, or a live-capital
system. Its learning loop is deliberately slow because its sample size demands it.
Its ML overlay is probationary and may never ship. That is by design.
