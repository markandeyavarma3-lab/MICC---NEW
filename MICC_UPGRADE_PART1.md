# MICC Ultra-Advanced Upgrade — Part 1 Execution Plan (Pin-to-Pin)

> Status: **BUILT — all 7 stages complete, verify_phases 49/49 green (2026-07).**
> Wired into run_pipeline (daily `idea_cards`; weekly `index_membership` +
> `top500_sectors`). Stage 5 automation scripts in `automation/` (register once as
> admin; not auto-run). Author: pipeline audit, 2026-07-01.
> Scope: Part 1 (Foundation & Idea Engine core). Part 2 (signal depth) and Part 3
> (learning loop / risk / ML overlay) are explicitly deferred — see §Deferred.

---

## 0. Reality check — what the architecture doc got wrong

The source doc was written **without repo access** and assumed the foundation was
missing. Verified against `D:\MICC\marketDB\db\market.db` (91 tables) and the repo, most
of it already exists. This plan targets only the genuine gaps.

| Doc claim ("gap") | Actual state | Verdict |
|---|---|---|
| No Parquet lake | `data_storage/parquet/` has **10,259 files**, year-partitioned 2005→now | ✅ done |
| Adopt DuckDB | `data_storage/duckdb/micc.duckdb` (1.6 GB) live | ✅ done |
| No PIT survivorship-free universe | `pit_universe` 359k rows, monthly rebal from 2005, mkt-cap/turnover rank buckets | ✅ done (rank-based) |
| No adjusted / TR prices | `stock_data_adj`, `stock_data_tr` (7.65M each) | ✅ done |
| No as-of feature store | `features_monthly` (344k), `fundamentals_pit` (71k) | ✅ done |
| No pin-to-pin tests | `common/verify_phases.py` re-derives claims PASS/FAIL | ✅ done (extend it) |
| No ATR for bands | `symbol_technicals.atr_14_pct` present | ✅ available |
| **No named PIT index membership** | `index_constituents` = current snapshot only, no change-dates | ❌ **build** |
| **No Idea Engine model** | `recommendations` (555 rows) is flat; no thesis/trade | ❌ **build** |
| **No versioned scoring** | score computed inline in `generate_signals.py` (`mean pct-rank ×100`) | ❌ **build** |
| **Fixed σ bands / 1-mo horizon** | `recommendations.py`: `TARGET_SIG=1.5`, `STOP_SIG=1.0`, `HORIZON_TD` fixed | ❌ **upgrade** |
| **Sector coverage** | `dim_sector` = 1,409 / 2,372 tradable = **59%** | ❌ **raise** |
| **No automation** | no `.github/workflows`; `run_pipeline.py` run by hand | ❌ **automate** |

**Net:** Part 1 is *not* "rebuild the foundation." It is **Idea Engine + scoring
framework + 4 hardening items** on top of a foundation that already holds.

### Decisions locked with owner (2026-07-01)
1. Deliver this written plan **before building**.
2. Automate via **Windows Task Scheduler** (data is 19 GB local; GitHub Actions can't reach it).
3. **Build named NIFTY 50/500 PIT membership** *in addition to* the rank-based universe.
4. **Defer the ML/CPCV overlay to Part 3.** Part 1 scoring core stays transparent-linear.

### Amendments folded in from blueprint review (2026-07-01)
The blind blueprint and this repo-grounded plan were reconciled; the plan wins on
facts (repo access). Four amendments applied:
- **A1 — Reorder** so PIT tests protect every later stage and the riskiest task
  (named membership, ~10–15% error) isn't rushed last:
  `0 → 1C → 2 → 3 → 4 → 1A/1B → 5 → 6`.
- **A2 — Split the scoring pillar** `trend_regime` into **`trend_align`** (single-stock
  trend) and **`regime_align`** (macro 4-vote gate) → **6 pillars**, weights still sum to 1.0.
  Avoids surgically un-merging a pillar in Part 2.
- **A3 — Hard-number the fundamentals cap:** value/quality theses **cannot exceed
  confidence 70/100 until ≥ 8 years of annual fundamentals coverage** exists for the
  symbol. Enforced in Stage 4 with an auditable `score_weights` rationale row.
- **A4 — Persist the ATR `k` multiplier per trade** (new `trade.atr_k` column) so Part 3's
  learning loop can re-calibrate without backfilling.
Corrected constants (repo-verified): **555** recommendations, **59%** sector coverage,
**Task Scheduler** (not GitHub Actions).

---

## Guiding principles (apply to every stage)
- **Additive, never destructive.** New tables/columns only; never drop or mutate an
  existing verified table. `market.db` stays system-of-record.
- **Idempotent.** Every builder = `CREATE TABLE IF NOT EXISTS` + `INSERT OR REPLACE`
  on a stable PK, re-runnable with identical results (house style, matches all fetchers).
- **PIT-correct.** No same-day-close → same-day-fill. Every as-of join lagged and
  regression-tested in `verify_phases.py`.
- **Auditable.** Every score is reproducible from a versioned weights row + persisted
  per-pillar contributions. No opaque numbers.
- **Run interpreter:** `py -3.14` (has nselib/fredapi/duckdb). DB: `D:\MICC\marketDB\db\market.db`.

---

## Stage 0 — Pre-flight (0.5 day)
**Goal:** safe workspace + a recoverable snapshot before touching a 19 GB DB.

1. Branch: `git checkout -b feat/part1-idea-engine`.
2. Schema snapshot: dump `SELECT sql FROM sqlite_master` → `data_extraction/schema_snapshot_pre_part1.sql` (committed, gitignore-exempt) for diffing later.
3. Backup marker: record row counts of the 12 tables Part 1 will read/extend into `monitoring_log` (tag `pre_part1_baseline`) so any regression is detectable.
4. New module dir: `data_extraction/ideas/` for the Idea Engine (keeps it separate from `events/`, `registry/`, `common/`).

**Acceptance:** branch exists; snapshot file diffs clean against a fresh dump; baseline row counts logged.
**Rollback:** `git checkout main`; no DB writes yet.

---

## Stage 1 — PIT correctness hardening (3–4 days)
Depends on: Stage 0. Three independent sub-tasks; can be built in parallel.

### 1A. Named PIT index membership
**New file:** `data_extraction/registry/build_index_membership.py`
**New table:** `index_membership`
```sql
CREATE TABLE IF NOT EXISTS index_membership (
  index_name   TEXT,      -- 'NIFTY 50','NIFTY 500','NIFTY SMALLCAP 250'
  symbol       TEXT,
  effective_from TEXT,    -- ISO date membership began
  effective_to   TEXT,    -- ISO date membership ended (NULL = still a member)
  method       TEXT,      -- 'reconstructed_mktcap' | 'official' | 'wikipedia_changelog'
  confidence   REAL,      -- 0..1 reconstruction confidence
  fetched_at   TEXT,
  PRIMARY KEY (index_name, symbol, effective_from)
);
```
Steps:
1. Reconstruct monthly membership from bhavcopy market-cap ranking (reuse the exact
   ranking already in `pit_universe`: top-50 → NIFTY 50 proxy, top-500 → NIFTY 500).
   This is a *derivation over an existing verified table*, not new scraping.
2. Cross-check current membership against `index_constituents` (must match ~100%).
3. Cross-check NIFTY 50 history against the free Figshare/HuggingFace 2008+ constituents
   dataset + Wikipedia change-log; store agreement as `confidence`.
4. Collapse month-by-month flags into `effective_from`/`effective_to` intervals.

**Acceptance (added to `verify_phases.py`):**
- Current `index_membership` (effective_to IS NULL) matches `index_constituents` for NIFTY 50 at 100%, NIFTY 500 ≥ 98%.
- Historical spot-checks (5 known additions/deletions, e.g. a 2018 & 2021 NIFTY 50 change) resolve to the correct `effective_from` ± 1 month.
- No symbol has overlapping intervals for the same index.

### 1B. Sector coverage 59% → ≥ 90%
**Edit:** `data_extraction/registry/build_sector_map.py` (extends `dim_sector`).
Steps: backfill missing 963 symbols from (a) `index_constituents.industry`, (b) NSE
`/api/equity-meta` industry, (c) BSE classification, (d) manual override CSV for the residual tail.
**Acceptance:** `COUNT(dim_sector) / COUNT(tradable_eq_stocks) ≥ 0.90`; no symbol maps to NULL/`'Unknown'` inside the current top-500 `pit_universe`.

### 1C. PIT regression tests
**Edit:** `data_extraction/common/verify_phases.py` — add a Phase-6 block:
- Membership: for 3 random (symbol, rebal_date) pairs, assert the stock was actually
  in the named index on that date per `index_membership` before any index-relative feature uses it.
- Fundamentals as-of: assert every `fundamentals_pit.pit_date` ≥ `report_date` (filing lag never negative), and that no feature row at `rebal_date R` consumes a fundamental with `pit_date > R`.
**Acceptance:** suite runs green; new checks count printed in the PASS/FAIL summary.

---

## Stage 2 — Idea Engine data model (4–5 days) ← highest value
Depends on: Stage 0. This is the core of Part 1.

**New files:** `data_extraction/ideas/schema.py` (DDL + migrations),
`data_extraction/ideas/backfill_recommendations.py` (one-shot migration).

### Tables
```sql
CREATE TABLE IF NOT EXISTS thesis (
  thesis_id     INTEGER PRIMARY KEY,
  created_at    TEXT,
  symbol        TEXT,            -- single-name (basket support deferred to Part 2)
  thesis_type   TEXT,            -- momentum|value|quality|event|macro_overlay
  source_signal TEXT,            -- strategy/factor that fired
  timeframe_class TEXT,          -- 'swing' (1-4wk) | 'positional' (1-3mo)
  regime_at_creation TEXT,       -- snapshot of 4-vote gate, e.g. 'RISK-ON 3/4'
  confidence_score REAL,         -- 0..100, from Stage 4 scorer
  weight_version   TEXT,         -- FK-ish -> score_weights.version used
  narrative     TEXT,
  status        TEXT,            -- active|closed|invalidated
  invalidation_condition TEXT,   -- explicit, e.g. 'close < 200DMA'
  closed_at     TEXT
);
CREATE TABLE IF NOT EXISTS trade (
  trade_id     INTEGER PRIMARY KEY,
  thesis_id    INTEGER,          -- FK -> thesis.thesis_id
  entry_date   TEXT,
  entry_price  REAL,
  stop         REAL,
  target       REAL,
  size_shares  INTEGER,          -- integer shares (matches paper_trader)
  atr_k        REAL,             -- ATR multiplier used for the stop (A4: for Part-3 recalibration)
  exit_date    TEXT,
  exit_price   REAL,
  exit_reason  TEXT,             -- target|stop|regime_liquidation|thesis_invalidated|expired
  realized_return REAL
);
-- idea_card = presentation view (materialized on refresh), NOT a hand-maintained table
CREATE TABLE IF NOT EXISTS idea_card (
  card_date    TEXT,
  thesis_id    INTEGER,
  symbol       TEXT, company TEXT, sector TEXT,
  thesis_type  TEXT, timeframe_class TEXT,
  entry REAL, stop REAL, target REAL, rr_ratio REAL, size_shares INTEGER,
  confidence_score REAL,
  pillar_json  TEXT,             -- per-pillar breakdown (Stage 4), for "why this score"
  status TEXT,
  PRIMARY KEY (card_date, thesis_id)
);
```

### Backfill (preserve the 49% track record)
`backfill_recommendations.py`: map each of the 555 `recommendations` rows →
one `thesis` (type=`strategy`, timeframe from `horizon_days`: ≤21→swing else positional)
+ one `trade` (entry/stop/target/exit from the rec, realized_return carried over).
**Acceptance (verify_phases Phase-7):**
- `COUNT(thesis) == 555` after backfill; every `trade.thesis_id` resolves.
- Σ `trade.realized_return` on CLOSED backfilled trades reproduces the current
  `recommendations` mean return within 1e-6 (no data lost in migration).
- Hit-rate recomputed from `trade` matches the documented 49%.
**Rollback:** tables are new; `DROP TABLE thesis; trade; idea_card;` restores prior state exactly (recommendations untouched).

---

## Stage 3 — ATR bands + auto timeframe (2 days)
Depends on: Stage 2. Replaces the fixed-σ / 1-month logic.

**Edit:** `data_extraction/common/recommendations.py` (or new `ideas/build_bands.py`
that supersedes the band block). Uses `symbol_technicals.atr_14_pct` (already present).

Rules:
- `timeframe_class`: momentum/breakout **and** strong trend (`adx_14 ≥ 25` & `above_200`) → **positional**; otherwise → **swing**.
- ATR multiplier `k`: swing → 1.5–2.0×, positional → 2.5–3.0× (starting values, flagged for re-calibration on MICC's own closed-trade data — not laws).
- `stop = entry × (1 − k × atr_14_pct)`; `target = entry × (1 + R × k × atr_14_pct)` with R surfaced as 1:1/1:2/1:3 on the card.
- `size_shares = floor( risk_budget_per_idea / (entry − stop) )` — equal-risk sizing, integer shares (matches `paper_trader`).

**Acceptance:**
- Every open idea card has `stop < entry < target`, `rr_ratio ∈ {1,2,3}` (±rounding), `size_shares ≥ 1`.
- Two stocks with equal `risk_budget` but 2× ATR ratio get ~½ the share count (equal-risk invariant, asserted in verify).
- Backtest parity guard: re-running the flagship backtest with ATR bands does not silently change historic `bt_metrics` (new columns, old strategy untouched).

---

## Stage 4 — Versioned linear scoring framework (3–4 days)
Depends on: Stage 2 (needs thesis rows to score). **Framework only** — placeholder
weights; Part 2 populates real sub-scores, Part 3's loop updates weights.

**New file:** `data_extraction/ideas/scoring.py`.
```sql
CREATE TABLE IF NOT EXISTS score_weights (
  version      TEXT,     -- e.g. 'v1.0'
  pillar       TEXT,     -- signal_strength|trend_regime|liquidity_capacity|confirmation|risk_penalty
  weight       REAL,     -- Σ over pillars per version = 1.0
  effective_date TEXT,
  rationale    TEXT,
  PRIMARY KEY (version, pillar)
);  -- pillar ∈ {signal_strength, trend_align, regime_align, liquidity_capacity, confirmation, risk_penalty}  (A2: 6 pillars)
CREATE TABLE IF NOT EXISTS score_audit (
  thesis_id    INTEGER,
  card_date    TEXT,
  pillar       TEXT,
  subscore     REAL,     -- 0..100
  weight       REAL,
  contribution REAL,     -- subscore × weight
  weight_version TEXT,
  PRIMARY KEY (thesis_id, card_date, pillar)
);
```
- **Pillars — 6, each 0–100 (A2):** `signal_strength` (primary factor percentile — seeded
  from the existing `generate_signals` composite), `trend_align` (single-stock trend:
  `above_200`, `adx_14`, dist-from-SMA), `regime_align` (macro 4-vote gate agreement),
  `liquidity_capacity` (capacity model / `med_turnover`), `confirmation` (delivery %,
  breadth), `risk_penalty` (vol/drawdown, negative-weighted).
- **Composite** = `Σ weight_i × subscore_i` → `confidence_score` on thesis/idea_card.
- Persist per-pillar to `score_audit`; dashboard renders "why this score" (exact, since linear).
- **Fundamentals cap (A3):** for `thesis_type ∈ {value, quality}`, `confidence_score` is
  hard-clamped to **≤ 70** unless the symbol has **≥ 8 years of annual fundamentals**
  (`annual_income` distinct fiscal years ≥ 8). The cap and its threshold live in a
  `score_weights` rationale row (version-scoped, auditable) — not buried in code.
- **Guardrails (in code):** weights per version sum to 1.0 (asserted); `risk_penalty`
  weight ≤ 0; a re-weighting helper caps any single-cycle weight move (used by Part 3, stubbed now).

**Acceptance:**
- Recompute any thesis's `confidence_score` from `score_audit` rows = stored value (exact).
- Seed `v1.0` weights reproduce today's `generate_signals` ranking order for the current top-decile book (framework is a strict generalization of the current inline score, not a behavior change).
- A synthetic value thesis on a symbol with < 8yr annual data is clamped to ≤ 70 (cap asserted in `verify_phases.py`).

---

## Stage 5 — Automation via Task Scheduler (1–2 days)
Depends on: Stages 1–4 landing in `run_pipeline.py`. Local, per owner decision.

**New files:** `automation/run_daily.ps1`, `automation/run_weekly.ps1`,
`automation/register_tasks.ps1`, `automation/heartbeat.py`.
1. Wrapper scripts set env (incl. `ALPHAVANTAGE_KEY`, `FRED_API_KEY`), `cd` to repo,
   call `py -3.14 run_pipeline.py --daily` / `--weekly`, tee logs to `data_extraction/logs/`.
2. `register_tasks.ps1` creates two scheduled tasks (daily ~18:30 IST post-close,
   weekly Fri) via `Register-ScheduledTask` **run whether logged on or not** — this is
   the admin/`-RunLevel Highest` fix noted in memory; script self-elevates.
3. `heartbeat.py`: on success writes `monitoring_log` + optional email/webhook; on
   failure (non-zero exit) sends an alert (no silent failures — the doc's key warning).

**Acceptance:**
- `register_tasks.ps1` run once → both tasks visible in `schtasks /query`.
- A forced-fail run triggers exactly one alert; a green run writes one heartbeat row.
- **10 consecutive unattended green runs** before the manual run is retired (owner threshold).

---

## Stage 6 — Wire-in, dashboard, docs (1–2 days)
Depends on: Stages 2–5.
1. `run_pipeline.py`: add `ideas/build_idea_cards.py` to DAILY_PHASES (after `recos`),
   `registry/build_index_membership.py` + `build_sector_map` backfill to WEEKLY_PHASES.
2. `common/build_dashboard.py`: add an **Idea Cards** panel (entry/stop/target/RR,
   timeframe chip, confidence + expandable per-pillar "why"). Add an explicit UI banner
   separating *dashboard polish* from *validated OOS edge* (doc's honesty requirement).
3. `web/api.py`: expose `/api/ideas` (open cards) and `/api/thesis/<id>` (audit trail).
4. Update `README.md`, `MICC_TECHNICAL_REPORT.md`; append a "Part 1 done" section to `RESEARCH.md`.
**Acceptance:** `run_pipeline.py --check` green; dashboard renders cards with working
"why this score"; `/api/ideas` returns open cards; `verify_phases.py` all-green.

---

## Dependency graph & sequencing
```
Stage 0
  └─ Stage 1C (PIT/fundamentals as-of tests — protect every later stage)
       └─ Stage 2 (Idea Engine)
            ├─→ Stage 3 (ATR bands)
            └─→ Stage 4 (6-pillar scoring)
                 └─ Stage 1A/1B (named membership + sector; membership test joins 1C)
                      └─ Stage 5 (automation) ─→ Stage 6 (wire-in)
```
**Build order (A1): `0 → 1C → 2 → 3 → 4 → 1A/1B → 5 → 6`.** PIT tests go early so they
guard every later change; the Idea Engine + scoring (highest value) ship next; named
membership (riskiest, ~10–15% error) sits *alongside* the core rather than rushed last;
automation and wire-in close it out. Estimated total: **~3 weeks** solo, EOD-paced.
Note: 1C's *fundamentals* as-of tests land immediately; its *membership* test is added
when 1A creates `index_membership`.

## Acceptance gate for "Part 1 complete"
1. `verify_phases.py` green incl. new Phases 6 (PIT) & 7 (Idea Engine backfill parity).
2. `thesis`/`trade`/`idea_card`/`score_weights`/`score_audit`/`index_membership` all populated & idempotent.
3. Sector coverage ≥ 90%; named-membership current match 100% (NIFTY 50).
4. Every idea card's confidence reproducible from `score_audit`.
5. 10 consecutive green unattended scheduled runs.
6. Dashboard Idea Cards panel live with per-pillar audit.

## Explicitly deferred
- **Part 2:** populate real sub-scores — global/macro regime spine, event/institutional
  layers, ATR-multiplier re-calibration, signal-library expansion, basket theses.
- **Part 3:** Friday learning loop that updates `score_weights`; risk meta-engine;
  **ML/CPCV + deflated-Sharpe overlay** (must beat linear OOS or it never ships to live scoring).
- **Avoid entirely:** intraday anything; deep-learning/RL on monthly cross-sections;
  live broker execution (paper-only until the desk is validated); paid data; multi-region.

## Risks / caveats
- ATR multipliers (1.5–3×) and swing/positional day-bands are **conventional starting
  points** to re-calibrate on MICC's own closed trades — not laws.
- Named-index reconstruction carries ~10–15% historical error; `confidence` column makes
  it auditable, and the rank-based `pit_universe` remains the primary universe for backtests.
- Value/quality theses rest on fundamentals only from 2021/2024 — the scorer must **cap
  confidence** for fundamentals-dependent theses until depth improves (enforced in Stage 4).
- Free-tier / NSE-scraping fragility unchanged from today; automation adds failure alerts
  so breakage is visible, not silent.
```
