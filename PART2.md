# MICC — Part 2: Signal & Engine Depth (As-Built Reference)

**Status:** ✅ Complete · `verify_phases.py` **72/72 green** (was 54 after Part 1)
**Date:** 2026-07 · **DB:** `D:\marketDB\db\market.db` · **Interpreter:** `py -3.14`

As-built record of Part 2 — what exists and, more importantly, **what earned scoring
weight vs what got demoted to context under the pre-registered discipline rule**:

> *Every proposed signal must pass a pre-registered walk-forward test (t ≥ 3.0)
> before it earns scoring weight; everything else is a context tag with zero weight.*

---

## 1. The verdict scoreboard (the honest heart of Part 2)

| Challenger | Test (pre-registered) | Result | Verdict |
|---|---|---|---|
| **Multi-axis regime spine** | WF-gated OOS Sharpe vs incumbent 4-vote gate, same books/months | IV **1.42 vs 1.53**, EW 1.37 vs 1.56 | ❌ **NO-SHIP** — 4-vote gate stays; spine = context |
| **Insider cluster buys** | 21d abnormal return: mean>0, t≥3, H2>0 | **+2.97%, t=3.67**, H2 +5.67% | ✅ **SCORED** — new `event_score` pillar |
| **Amihud illiquidity** | monthly rank-IC: sign +, t≥3, H2 same sign | IC **−0.020** (t=−2.4) — *wrong sign* | ❌ context — premium reverses inside a liquidity-filtered top-500 |
| **RS vs sector (6m)** | same IC rule | IC +0.013, t=1.37, decaying | ❌ context |
| **PEAD (true SUE)** | needs ≥12 quarters of PIT earnings | only ~5.5 quarters local depth | ⏸ **context pending depth** (proxy built, auto-upgradeable) |
| Buyback / index-inclusion / bulk deals / PCR / max-pain / FII futures L-S / calendar | per doc: thin data or lore-only | — | context tags / killed |
| **Pledge (invoke/new ≥1cr)** | risk-flag evidence (vol/credit), not alpha | 9,314 flags | ⚠️ feeds `risk_penalty` |

Four challengers tested, **one survived**. The proven momentum edge and the 4-vote
gate were never touched — Part 2's job was depth with discipline, not complexity.

## 2. New tables

| Table | Rows | Tier | Source |
|---|---|---|---|
| `regime_daily` | 4,608 days (2007→now) | context | 6 bounded trailing axes (risk/vol/fx/commodity/rates/flow); GFC 17, COVID 16, taper-tantrum 31 = risk_off ✓ |
| `spine_validation` | verdict | — | NO-SHIP recorded; scoring can never silently consume the spine |
| `event_signals` | 14,897 | mixed | 5 builders, each `evidence_tier`-graded (scored/context/risk) |
| `event_validation` | verdict | — | insider study: n=2,456, +2.97%, t=3.67 |
| `signal_candidate_validation` | verdicts | — | amihud & rs_sector IC results |
| `sector_regime_daily` | 68,385 | context | 15 sectors: 63d RS vs NIFTY, RS-momentum, RRG quadrant, breadth |
| `macro_sensitivity` | 14,850 | display | monthly 252d OLS betas (market/USDINR/Brent/US10Y/DXY) + t-stats |

## 3. Scoring v2.0 (Module 7)

`score_weights` version **v2.0** (v1.0 preserved — versioned history):

| pillar | v1.0 | v2.0 | change |
|---|---|---|---|
| signal_strength | 0.40 | **0.35** | unchanged source (flagship composite, frozen) |
| trend_align | 0.20 | **0.18** | unchanged |
| regime_align | 0.15 | **0.15** | **now the VALIDATED 4-vote gate** (votes/4×100, as-of) — fixes the breadth double-count; spine NO-SHIP |
| confirmation | 0.15 | **0.12** | unchanged |
| liquidity_capacity | 0.10 | **0.10** | unchanged |
| **event_score** | — | **0.10** | NEW: scored events only (insider clusters), linear recency decay over 63d, 50 = neutral |
| risk_penalty | −0.10 | **−0.10** | + **active pledge flag** (+25 subscore within 126d) |

Positive weights still sum to 1.00; A3 fundamentals cap unchanged; every confidence
remains exactly reproducible from `score_audit`. `sector_align` (doc prior 0.02) was
**not** added — rs_sector failed its gate, so the sector engine is context-only.

**Context tags on idea cards** (`idea_card.context_json`, zero weight): regime-spine
label/score, sector RRG quadrant + breadth, active context events (pead_proxy, etc.).

## 4. Pipeline wiring

Daily: `regime_spine` → `events_layer` → `sector_eng` → … → `rec_sync` → `idea_cards`.
Weekly adds the three **ship-gate revalidations** (`spine_gate`, `insider_gate`,
`cand_gate`) — verdicts refresh weekly and tiers follow them automatically.
`rec_sync` (added this part) keeps the thesis/trade mirror in lockstep with the
legacy recommendations engine so P7 parity holds daily.

## 5. Verification — 54 → 72 checks

| Phase | Checks | Covers |
|---|---|---|
| **P10** | 4 | spine history/bounds, GFC+COVID re-derivation, ship-verdict consistency |
| **P11** | 5 | 5 builders present, ISO dates, tier==verdict, scored-only-with-t≥3, risk-direction |
| **P12** | 4 | sector history, RRG validity, breadth bounds, ≥10 sectors |
| **P13** | 6 | v1.0 preserved, event weight backed by passed study, zero context leak, no orphaned audits, regime_align == 4-vote re-derivation |

Also fixed en route: orphaned `score_audit` rows on thesis rebuild (cascade delete +
one-time cleanup of 276 orphans).

## 6. Known limitations (plain)

- **Insider effect caveats:** 49% hit rate (mean driven by a right tail) and the AR
  concentrates post-2021 (H1 +0.25% vs H2 +5.67%). Weight kept small (0.10) and the
  weekly re-study will demote it automatically if it decays below the rule.
- **PEAD proxy** is YoY-growth z, not Foster SUE — stays context until ≥12 quarters
  of PIT depth accumulate (~2028 at current collection rate, sooner if backfilled).
- Sector RS uses **equal-weight** member returns — reads hot vs the cap-weighted
  NIFTY during smallcap rallies; fine for context, not for benchmarking.
- `flow_axis` uses FII index-futures OI, and FII flows are trend-chasing/lagging —
  it carries 0.05 weight *inside a context-tier spine*, i.e. zero scoring impact.
- Buyback/announcement history is ~1 month deep locally; the builder is correct but
  starving until `corporate_announcements` accumulates.

## 7. Deferred to Part 3

Friday learning loop (proposes `score_weights` v2.x with per-cycle move caps), risk
meta-engine, ATR-k re-calibration on closed trades, ML/CPCV probationary overlay,
HMM challenger regime model, F&O scored signals, screener.in fundamentals deepening
(Module 6a — unbinds the value/quality ≤70 cap at ≥8yr depth).
