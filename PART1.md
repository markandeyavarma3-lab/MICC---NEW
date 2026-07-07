# MICC — Part 1: Idea Engine & Foundation Hardening (As-Built Reference)

**Status:** ✅ Complete · `verify_phases.py` **54/54 green** · branch `feat/part1-idea-engine`
(includes post-review hardening + owner sizing spec — see §9)
**Date:** 2026-07 · **DB:** `D:\MICC\marketDB\db\market.db` (system-of-record) · **Interpreter:** `py -3.14`

This is the **as-built** reference for Part 1 — what exists in the code and database
*right now*, not a plan. For the staged execution plan and design rationale see
[`MICC_UPGRADE_PART1.md`](MICC_UPGRADE_PART1.md).

---

## 1. What Part 1 is (and isn't)

Part 1 turns MICC from "a proven momentum backtest + a flat recommendations log" into
an **auditable idea desk**: every live idea is a *thesis* with ATR-derived entry/stop/
target bands, an auto-assigned timeframe, and a **transparent, reproducible confidence
score** you can fully explain pillar-by-pillar. It also hardens point-in-time (PIT)
correctness with named index membership and new regression tests.

**Deliberately NOT in Part 1** (deferred): real macro/event sub-scores (Part 2), the
Friday learning loop that updates weights, the risk meta-engine, and any ML/CPCV
overlay (Part 3). Also permanently avoided: intraday, deep-learning on monthly
cross-sections, live broker execution, paid data.

### The reality-check that reshaped the plan
The source architecture doc was written **without repo access** and assumed the whole
foundation was missing. Verification showed most of it already existed, so Part 1 was
re-scoped to the genuinely missing layer:

| Doc assumed missing | Actually already present | Action |
|---|---|---|
| Parquet lake | `data_storage/parquet/` — 10,259 files, 2005→now | none |
| DuckDB | `data_storage/duckdb/micc.duckdb` (1.6 GB) | none |
| PIT survivorship-free universe | `pit_universe` (359k rows, monthly from 2005) | none |
| Adjusted / total-return prices | `stock_data_adj`, `stock_data_tr` (7.65M each) | none |
| As-of feature store | `features_monthly` (344k), `fundamentals_pit` (71k) | none |
| ATR indicator | `symbol_technicals.atr_14_pct` | reuse |
| Idea Engine (thesis/trade) | — | **BUILT** |
| Versioned scoring | score was inline in `generate_signals.py` | **BUILT** |
| Named PIT index membership | `index_constituents` = current snapshot only | **BUILT** |
| Automation | manual `run_pipeline.py` | **BUILT** (Task Scheduler) |

### Reviewer amendments folded in
1. **A1 — build order** `0 → 1C → 2 → 3 → 4 → 1A/1B → 5 → 6` (PIT tests early).
2. **A2 — 6 pillars**: split `trend_regime` into `trend_align` + `regime_align`.
3. **A3 — hard fundamentals cap**: value/quality ≤ 70 until ≥ 8yr annual data.
4. **A4 — persist `atr_k`** per trade for later re-calibration.

---

## 2. Data model (new tables)

All additive; no existing table was dropped or mutated. DDL lives in
[`data_extraction/ideas/schema.py`](data_extraction/ideas/schema.py).

### 2.1 `thesis` — one row per conviction (durable unit the learning loop scores)
| column | type | notes |
|---|---|---|
| `thesis_id` | INTEGER PK | autoincrement |
| `created_at` | TEXT | ISO date the thesis was formed |
| `symbol` | TEXT | single name (basket support = Part 2) |
| `thesis_type` | TEXT | `momentum` \| `value` \| `quality` \| `event` \| `macro_overlay` |
| `source_signal` | TEXT | strategy/factor that fired |
| `timeframe_class` | TEXT | `swing` (1–4wk) \| `positional` (1–3mo) |
| `regime_at_creation` | TEXT | snapshot of the 4-vote gate |
| `confidence_score` | REAL | 0–100 (Stage 4 scorer) |
| `weight_version` | TEXT | which `score_weights.version` produced the score |
| `narrative` | TEXT | also used as a provenance tag (`backfill:recommendations`, `live:momentum_bands`) |
| `status` | TEXT | `active` \| `closed` \| `invalidated` |
| `invalidation_condition` | TEXT | explicit, e.g. `close below stop 8220.66` |
| `closed_at` | TEXT | |

**Current contents:** 601 rows = 555 backfilled (legacy recs) + 46 live band theses.

### 2.2 `trade` — many rows per thesis (entries/exits/tranches)
| column | type | notes |
|---|---|---|
| `trade_id` | INTEGER PK | |
| `thesis_id` | INTEGER | FK → `thesis` |
| `entry_date`, `entry_price` | | |
| `stop`, `target` | REAL | |
| `size_shares` | INTEGER | integer shares (matches paper_trader) |
| `atr_k` | REAL | **A4** — ATR multiplier used for the stop |
| `exit_date`, `exit_price` | | |
| `exit_reason` | TEXT | `target`\|`stop`\|`regime_liquidation`\|`thesis_invalidated`\|`expired` |
| `realized_return` | REAL | |

### 2.3 `idea_card` — materialised presentation view (rebuilt every run, never hand-edited)
`card_date, thesis_id, symbol, company, sector, thesis_type, timeframe_class, entry,
stop, target, rr_ratio, size_shares, confidence_score, pillar_json, status`
PK `(card_date, thesis_id)`. `pillar_json` holds the per-pillar "why this score" breakdown.

### 2.4 `score_weights` — versioned linear-composite weights
`version, pillar, weight, effective_date, rationale` · PK `(version, pillar)`.
Seeded version **v1.0** (7 rows: 6 pillars + a `_fund_cap` meta-row storing the A3 threshold).

### 2.5 `score_audit` — per-pillar contribution for every scored thesis
`thesis_id, card_date, pillar, subscore, weight, contribution, weight_version` ·
PK `(thesis_id, card_date, pillar)`. Makes every confidence number exactly reproducible.

### 2.6 `index_membership` — named PIT index membership (Stage 1A)
`index_name, symbol, effective_from, effective_to, method, confidence, fetched_at` ·
PK `(index_name, symbol, effective_from)`. `effective_to IS NULL` = still a member.
**13,161 rows** = 1,100 official-current + 12,061 historical. Sources by method:
**`niftyindices_official`** (NIFTY 50, **confidence 1.0** — real survivorship-free data,
100 distinct symbols 2008→2025); **`reconstructed_turnover`** (NIFTY 100/200/500,
confidence = measured agreement 0.63/0.80/0.78); **`official`** (current snapshot, 1.0).
A companion **view `index_membership_consumable`** exposes only `confidence ≥ 0.75` — the
*only* membership Part 2 signals may join (weak NIFTY 100 turnover history is quarantined).

---

## 3. Stage-by-stage — what was built and how it's proven

### Stage 0 — Pre-flight
- Branch `feat/part1-idea-engine`; new `data_extraction/ideas/` module dir.
- `data_extraction/schema_snapshot_pre_part1.sql` — full pre-change schema (136 objects) for diffing.
- Baseline row counts of 12 touched tables logged to `monitoring_log` (`pre_part1_baseline`).

### Stage 1C — PIT / fundamentals as-of regression tests
Extended [`common/verify_phases.py`](data_extraction/common/verify_phases.py) with **Phase 6**:
- `fundamentals_pit.pit_date ≥ report_date` (a result can't be known before it's filed) — **0 violations**.
- `pit_date` clean ISO; **median filing lag 42 days** over 1,988 rows (spot-on for Indian quarterly results).

### Stage 2 — Idea Engine + backfill
- [`ideas/schema.py`](data_extraction/ideas/schema.py) — idempotent DDL for all 5 tables.
- [`ideas/backfill_recommendations.py`](data_extraction/ideas/backfill_recommendations.py) —
  maps each of the **555** legacy `recommendations` → 1 thesis + 1 trade. `realized_return`
  copied verbatim, so the migration is loss-free. Idempotent via provenance-tag reset.
- **Proof (P7):** thesis=555, 0 orphan trades, mean-return parity `|rec−trade| = 0.0` (exact).

### Stage 3 — ATR bands + auto timeframe
[`ideas/build_bands.py`](data_extraction/ideas/build_bands.py). Reads the live book
(`current_signals` where `in_portfolio=1`) and daily ATR (`symbol_technicals.atr_14_pct`,
**in percent**). For each name:

```
timeframe = positional  if  adx_14 ≥ 25 AND price > 200DMA
            swing        otherwise
k         = 2.75 (positional) | 1.75 (swing)        # conventional, re-calibrate later (A4)
atr_frac  = atr_14_pct / 100
stop      = round(entry * (1 − k*atr_frac), 2)
stop_dist = entry − stop                            # rounded distance drives all downstream
target    = round(entry + R*stop_dist, 2)           # R = 2.0  →  reward:risk = 2:1
size      = floor(RISK_BUDGET / stop_dist)          # RISK_BUDGET = ₹10,000 equal risk/idea
```

`atr_k` is stored on every trade. **Proof (P8):** 46 cards (37 positional / 9 swing),
`stop<entry<target` all, size≥1 all, reward:risk = 2.00 exactly, equal rupee-risk holds,
`atr_k` persisted.

> Rounding-order note: sizing and target are derived from the **rounded** stop distance,
> so the equal-risk invariant holds exactly (an earlier version that sized off the
> unrounded distance failed its own check — fixed).

### Stage 4 — 6-pillar versioned linear scorer (the hard part)
[`ideas/scoring.py`](data_extraction/ideas/scoring.py).

```
confidence = clamp( Σ_pillar  weight_pillar × subscore_pillar , 0, 100 )
then A3 fundamentals cap
```

**v1.0 weights** (positive weights sum to 1.0; `risk_penalty` negative):

| pillar | weight | subscore source |
|---|---|---|
| `signal_strength` | **+0.40** | `current_signals.score` (the momentum composite) |
| `trend_align` | +0.20 | `0.5·clamp(50+pct_above_sma200) + 0.5·clamp(2·adx_14)` |
| `regime_align` | +0.15 | `market_breadth.pct_above_200dma` (macro proxy — Part 2 refines) |
| `confirmation` | +0.15 | delivery % (`deliv_1m`) |
| `liquidity_capacity` | +0.10 | percentile of `med_turnover` within the book |
| `risk_penalty` | **−0.10** | `clamp(10 × atr_14_pct)` (volatility drag) |

**A3 fundamentals cap:** for `thesis_type ∈ {value, quality}`, confidence is clamped to
**≤ 70** unless the symbol has **≥ 8 distinct years** in `annual_income`. Max coverage
today is **5 years**, so the cap binds on *every* value/quality idea — the honest,
intended behavior. The threshold is stored as an auditable `score_weights._fund_cap` row.

**Guardrails:** positive weights must sum to 1.0 (asserted), `risk_penalty ≤ 0` (asserted).

**Proof (P9):** all 46 confidences reproduce exactly from `score_audit`; weight
integrity holds; the A3 cap binds (`20MICRONS` value 95→70); and with a **degenerate
weight set** (`signal_strength=1`, rest 0) the composite reproduces the `generate_signals`
ranking exactly — proving the framework is a strict *generalization* of the old inline
score, not a behavior change.

### Stage 1A/1B — named PIT index membership + sector
[`registry/build_index_membership.py`](data_extraction/registry/build_index_membership.py) —
**hybrid, and honest about accuracy**:
- **Current** membership taken verbatim from `index_constituents` (`method='official'`,
  `confidence=1.0`, `effective_to=NULL`) for NIFTY 50/100/200/500 + NEXT 50 + MIDCAP 100
  + SMALLCAP 100.
- **Historical** membership reconstructed month-by-month from `pit_universe` turnover
  rank (`adv_rank`), collapsed into `effective_from/to` islands. `method='reconstructed_turnover'`.
- **Honesty:** turnover rank is a *weak* proxy for NIFTY 50 — measured **~58% agreement**
  with the official current list (turnover ≠ market cap). So historical confidence is set
  **low on purpose** (NIFTY 50 = 0.60, NIFTY 500 = 0.80) so downstream code can filter it
  out. The doc's optimistic "85–90%" (which assumed market-cap ranking) is **not** claimed.
  The rank-based `pit_universe` remains the primary backtest universe.

[`registry/backfill_top500_sectors.py`](data_extraction/registry/backfill_top500_sectors.py) —
the 6 residual top-500 names without a sector turned out to be **ETFs** (gold/silver/index
funds that enter by turnover); tagged `sector='ETF'`. **Overall coverage stays ~60% by
design** — the missing ~950 names are the illiquid equity tail *outside* the tradable
top-500, for which no free sector source exists and which the Idea Engine never scores.

**Proof (P6):** NIFTY 50 current = **100%** official, **0** overlapping intervals,
`effective_to ≥ effective_from` always, **0** NULL sectors inside the current top-500.

### Stage 6 — Wire-in
- [`ideas/build_idea_cards.py`](data_extraction/ideas/build_idea_cards.py) — **daily
  orchestrator**: `build_bands` → `scoring` → materialise `idea_card` (with `pillar_json`).
- [`run_pipeline.py`](data_extraction/run_pipeline.py): daily phase `idea_cards` (after
  `recos`); weekly phases `index_membership` + `top500_sectors`.
- [`web/api.py`](data_extraction/web/api.py): `GET /api/ideas` (live cards + pillar
  breakdown) and `GET /api/thesis/{id}` (thesis + trades + full score audit).
- [`common/build_dashboard.py`](data_extraction/common/build_dashboard.py): an **Idea
  Cards** panel (entry/stop/target/RR, timeframe, confidence, top-2 "why" pillars) and a
  prominent **honesty banner** — *"Dashboard polish ≠ validated edge."*

### Stage 5 — Automation (Task Scheduler)
`automation/` — see [`automation/README.md`](automation/README.md).
- `run_daily.ps1` / `run_weekly.ps1` — pipeline wrappers (env, logging, heartbeat).
- `heartbeat.py` — one `monitoring_log` row per run; **failure webhook** via
  `MICC_ALERT_WEBHOOK` (no silent failures — Task Scheduler gives none by default).
- `register_tasks.ps1` — self-elevating one-time registration of `MICC-Daily` (18:30) and
  `MICC-Weekly` (Fri 19:00), `S4U + RunLevel Highest` = run whether logged on or not.

> **Not auto-run.** Registering scheduled tasks is a system change requiring admin — run
> `register_tasks.ps1` yourself once, then watch for **10 consecutive green heartbeats**
> before retiring the manual run.

---

## 4. The verification suite — 49/49

`py -3.14 common/verify_phases.py` re-derives every claim from raw tables (it does not
trust prior printouts). Part 1 grew it from 29 → **49** checks:

| Phase | Checks | Covers |
|---|---|---|
| P1–P5 | 29 | existing: adj prices (cadence-robust, §9), PIT universe, ISIN, features, backtest |
| **P6** | 9 | fundamentals as-of, membership intervals, NIFTY 50 match, top-500 sector, consumable-view quarantine |
| **P7** | 3 | idea-engine backfill parity (exact) + no orphan trades |
| **P8** | 8 | ATR bands (order, size, 2:1 RR, `atr_k`) + **risk caps** (stop ≤ 10%, risk ≤ budget, position + portfolio capital caps) |
| **P9** | 5 | scoring reproducibility, weight integrity, A3 cap, degenerate-weights == generate_signals |

**Total: 54/54.**

---

## 5. API examples

```
GET /api/ideas
→ { "card_date": "2026-06-25", "n": 46, "cards": [
     { "symbol":"APOLLOHOSP","timeframe_class":"positional","entry":8592.0,
       "stop":8220.66,"target":9334.68,"rr_ratio":2.0,"size_shares":26,
       "confidence_score":73.66,
       "pillars":{ "signal_strength":{"subscore":86.2,"weight":0.4,"contribution":34.48}, ... } },
     ... ] }

GET /api/thesis/560
→ { "thesis": {...}, "trades": [ {entry, stop, target, size_shares, atr_k, ...} ],
    "score_audit": [ {pillar, subscore, weight, contribution, weight_version}, × 6 ] }
```

---

## 6. Reproduce Part 1 from scratch

```powershell
py -3.14 ideas\schema.py                        # create idea/scoring tables
py -3.14 ideas\backfill_recommendations.py      # 555 recs -> thesis+trade (exact parity)
py -3.14 registry\build_index_membership.py     # named PIT membership (hybrid)
py -3.14 registry\backfill_top500_sectors.py    # close top-500 sector gap
py -3.14 ideas\build_idea_cards.py              # bands -> scoring -> cards (the daily job)
py -3.14 common\build_dashboard.py              # dashboard incl. Idea Cards panel
py -3.14 common\verify_phases.py                # 49/49 acceptance gate
```

---

## 7. Known limitations (stated plainly)

- **Historical named membership ~58% accurate** for NIFTY 50 (turnover proxy). Use the
  `confidence` column to filter; do not use low-confidence rows for leakage-critical work.
- **Fundamentals depth is ~5 years** → every value/quality idea is confidence-capped at 70
  by A3 until depth improves. This is correct, not a bug.
- **Sector coverage ~60% overall** (top-500 is complete); the illiquid tail has no free
  source and is never scored.
- **ATR multipliers (1.75 / 2.75) and the ₹10k risk budget are placeholders** — designed
  to be re-calibrated on MICC's own closed trades in Part 3 (that's why `atr_k` is stored).
- **`regime_align` is a breadth proxy** — Part 2 replaces it with the full macro spine.

---

## 8. What's next

- **Part 2:** populate the real sub-scores — macro/global regime spine, event &
  institutional-flow layers, ATR-multiplier calibration, signal-library expansion, baskets.
- **Part 3:** the Friday learning loop that proposes new `score_weights` versions (with
  per-cycle move caps), the risk meta-engine, and a **probationary** ML/CPCV overlay that
  only ships to live scoring if it beats the linear composite out-of-sample.

---

## 9. Post-review hardening (2026-07)

Changes made in response to the Part-1 code review + an owner sizing spec.

**Review #1 — "0.60-confidence membership shouldn't be consumed" → fully fixed with real data.**
The reviewer's option (a) (market-cap reconstruction) was infeasible
(`stock_fundamentals.marketCap` is empty). Option (b) worked: the survivorship-free
**niftyindices** NIFTY 50 constituent-weights history exists on HuggingFace/Figshare
(`AMP4010/Historical_Nifty_50_Constituent_Weights_20Y`, CC BY-NC-SA).
- New fetcher [`registry/fetch_niftyindices_nifty50.py`](data_extraction/registry/fetch_niftyindices_nifty50.py)
  downloads it (retries once) to `data_storage/raw/niftyindices/`.
- [`build_index_membership.py`](data_extraction/registry/build_index_membership.py) now
  builds NIFTY 50 history from it (**`niftyindices_official`, confidence 1.0**) — 100
  distinct symbols 2008→2025, validated against known changes (VEDL two stints, ZEEL
  dropped ~2020, INFY continuous). This **replaces** the weak 58% turnover proxy for NIFTY 50.
- For NIFTY 100/200/500 (no free authoritative source) confidence is still **measured**
  (0.63/0.80/0.78). The **`index_membership_consumable`** view (conf ≥ 0.75) is the only
  table Part 2 signals may join; now only NIFTY 100 turnover history is quarantined.
- `verify_phases` P6 asserts the view leaks no `conf<0.75` row and keeps official members.

**Owner sizing spec (₹1 cr book, stops ≤ 10%, portfolio cap).**
- [`build_bands.py`](data_extraction/ideas/build_bands.py): stop distance capped so the
  **stop-loss is never > 10%** below entry; a **concentration cap** keeps any single
  position ≤ 10% of capital. `MICC_CAPITAL` (default ₹1,00,00,000) and `MICC_RISK_BUDGET`
  (default ₹10,000, review #3) are env-configurable.
- [`build_idea_cards.py`](data_extraction/ideas/build_idea_cards.py): a **portfolio-level
  capital cap** selects ideas by confidence (highest first) until the ₹1 cr book is filled;
  each card carries `notional` + `in_book` (1 = in the tradable book, 0 = waitlist).
- `verify_phases` P8 now asserts: stop-loss ≤ 10%, risk ≤ budget per idea, no position >
  concentration cap, and in-book notional ≤ capital. (Today: 46/46 fit, ₹70.9 L deployed.)

**Review #2 — regime_align (note only):** acknowledged breadth double-count; left as
placeholder, Part 2 replaces it. **Do not tune weights before then.**

**Cadence-robust adj check (found during review testing):** the daily raw update legitimately
leads the weekly `stock_data_adj` rebuild, which made the strict `n_adj == n_raw` check
false-alarm daily. It now asserts adj *covers* raw within its own date range (≤ 0.5%
pending-rebuild tolerance) and never *exceeds* raw.

**Suite total after hardening: 54/54.**
