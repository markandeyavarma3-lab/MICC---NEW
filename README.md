# MICC — Indian Equity Quant Research Platform

> From a **130-million-row** NSE/BSE + macro warehouse to a **walk-forward-validated** factor
> strategy and a live dashboard — survivorship-free, corporate-action-adjusted, point-in-time.

**Highlights**
- 🗄️ **130M+ row** warehouse (100+ tables, 19 GB): 21 yrs equity OHLCV + delivery, 69M-row F&O,
  37M-row MF NAV, macro, deals, events, insider filings — survivorship-free from 2005.
- 🧪 **Validated strategy**: momentum + delivery + low-vol composite, inverse-vol weighted, macro
  **regime-gated** → **out-of-sample Sharpe 1.53** (Calmar 1.26, MaxDD −19%, net of costs, 2009→2026).
- 🃏 **Live idea desk**: ₹1cr paper book, ATR-banded idea cards (stop ≤10%), 7-pillar auditable
  confidence, portfolio caps, drawdown/streak risk brakes — every number reproducible from audit tables.
- ⚖️ **Verdict-driven research**: every signal pre-registered (t≥3 walk-forward gate). **10 studies
  run, 1 survivor** (insider cluster buys). Regime spine, ML (CPCV), value/quality, amihud — all
  honestly killed with receipts.
- 🤖 **Self-governing**: scheduled daily/weekly pipeline, integrity-checked backups + restore drill,
  ntfy failure alerts, monitor-only learning loop, quarterly auto re-validations — **98/98 pin-to-pin verified**.
- 🖥️ **React frontend**: glassy dark 6-page SPA at `localhost:8765` (thesis drill-downs, verdict
  ledger, risk panels) on a live JSON API.

**Key docs:** [📄 Research paper](RESEARCH.md) · [🧭 Analysis blueprint](MICC_BLUEPRINT.md) ·
[🏗️ Part 1](PART1.md) · [📡 Part 2](PART2.md) · [🔁 Part 3](PART3.md) · [🛟 DR runbook](docs/DR_RUNBOOK.md) ·
[📊 Dashboard](MICC_dashboard.html) (open in a browser) · run `py -3.14 common/verify_phases.py` to audit.

---

## 🧭 The system today — complete state (as of 2026-07-03)

> The deep record of what was built across Parts 1–3 + the frontend, how it fits together,
> how to run it, and what honestly remains. Per-part detail: [PART1.md](PART1.md) ·
> [PART2.md](PART2.md) · [PART3.md](PART3.md). Dated entries: [Progress log](#progress-log) below.

### Architecture at a glance

```
  NSE/BSE/FRED/yfinance/screener  ──►  market.db (19GB, 100+ tables, system-of-record)
                                          │
        DAILY PIPELINE (Task Scheduler 18:30, ~30 phases)
        fetchers → adjusted prices → regime spine → event layer → sector engine
        → signals → recos → rec_sync → RISK STATE → IDEA CARDS → dashboard → monitor
                                          │
        WEEKLY (Fri 19:00): fundamentals, registries, PIT membership, backtests,
        screener PIT + VALUE GATE, Friday review, quarterly auto-gates, BACKUP
                                          │
  verify_phases.py (98 checks) ── ntfy alerts ── status.py ── React UI @ :8765
```

### Part 1 — the Idea Engine (built, verified)
- **Data model**: `thesis` (one row per conviction) → `trade` (entries/exits, `atr_k`
  persisted) → `idea_card` (materialised view with per-pillar JSON). 555 legacy
  recommendations backfilled with **exact return parity (0.0 diff)**; daily `rec_sync`
  keeps the mirror in lockstep.
- **Bands & sizing (owner spec)**: ATR-14 stops **capped at ≤10% below entry**, 2:1 reward:risk,
  equal rupee-risk ₹10k/idea, single position ≤10% of the **₹1cr capital**, book filled by
  confidence until the capital cap; `in_book` vs waitlist on every card.
- **Scoring**: versioned linear composite (`score_weights` v1.0→v2.0) with per-pillar
  `score_audit` — every confidence number recomputable exactly. A3 cap: value/quality ≤70.
- **Named index membership**: real niftyindices NIFTY 50 history 2008→2025 (conf 1.0),
  Wikipedia-bridged Sep-2025 reshuffle to present (conf 0.95, 96% validated); weak turnover
  proxies quarantined behind `index_membership_consumable` (conf ≥0.75 only).
- **Automation**: `MICC-Daily` (18:30) + `MICC-Weekly` (Fri 19:00) scheduled tasks,
  heartbeats to `monitoring_log`, **ntfy push alerts on failure**, per-phase runtime
  logging with timeout-headroom warnings in `automation/status.py`.

### Part 2 — signal depth under a discipline rule (built, verified)
> *Pre-registration governance: nothing scores without a registered test window, pass
> threshold and kill criteria (`signal_preregistration`, 13 signals). t ≥ 3.0 or context.*

| Challenger | Test | Result | Verdict |
|---|---|---|---|
| Multi-axis regime spine (6 axes) | WF OOS Sharpe vs 4-vote gate, same months | 1.42 vs **1.53** | ❌ NO-SHIP → context |
| **Insider cluster buys** | 21d abnormal-return event study | **+2.97%, t=3.67**, H2 +5.67% | ✅ **SCORED** |
| Amihud illiquidity | monthly rank-IC | IC **−0.020** (wrong sign in top-500) | ❌ context |
| RS vs sector | monthly rank-IC | +0.013, t=1.4 | ❌ context |

- **Event layer**: 14,897 evidence-tiered events (insider clusters, 9,314 pledge risk flags,
  PEAD proxy pending depth, buybacks, index inclusions). Strict PIT: `event_date < card_date`.
- **Scoring v2.0**: new `event_score` pillar (0.10, insider only, recency-decayed);
  `regime_align` = the **validated 4-vote gate** (fixes breadth double-count);
  pledge flags feed `risk_penalty`. Positive weights sum to 1.00; v1.0 preserved.
- **Context tier** (display, zero weight, verify-enforced): regime spine label/axes,
  15-sector RRG rotation engine, macro sensitivity betas, context event tags on cards.

### Part 3 — self-governance & the honest negatives (built, verified)
- **Exit calibration** on our own 540 closed trades: *whipsaw hypothesis falsified* — only
  **1%** of stopped trades later hit target; wider stops monotonically worse → **KEEP bands**.
  `trail_atr3` near-miss re-tested quarterly (auto-gated).
- **Risk meta-engine** (`risk_state_daily`, wired into sizing + card selection):
  DD brakes ×1.0/0.75/0.5/0.25 at 10/15/22% + **halt >22%**, 3-loss streak brake,
  concentration + correlation throttles. Current: +₹4.7L cum R-PnL, DD 3.9%, mult ×1.0.
- **Friday learning loop** (monitor-only *by design* — 10–30 trades/mo cannot support fast
  weight updates): weekly attribution + narrative; Bayesian shrinkage proposals hard-gated
  (κ=100, move cap ±0.02, **min 30 closed scored trades/pillar**, shadow + human approval).
  First review: 0 proposals — correct.
- **Fundamentals depth**: screener.in scrape (494 symbols × 12 FYs) → 44,740 PIT-tagged rows
  (FY-end+60d, all flagged estimated) → 397/411 validated vs yfinance → 356 cap-lift-eligible.
- **Value/quality re-backtest → FAIL**: 131 months, ICs ≈ 0 (t = 0.48 / −0.26 / 0.12) *even
  with the survivor tailwind* → **the ≤70 cap stays, evidence-backed**. Re-runs weekly.
- **ML/CPCV harness**: 15 purged paths — ridge 0.61 and LightGBM 0.80 median path Sharpe
  vs champion **1.00** → both **KILLED** (LGBM had DSR 0.92, Kendall-W 0.84 — still must beat
  the champion). Re-runs quarterly. Champion = the frozen linear composite, again.
- **Event shadow log**: 2,023 would-be event ideas accruing 21/63/126td outcomes;
  promotion gate: ≥12 months + ≥30 filled + beats 49% baseline (~mid-2027).
- **Ops**: weekly `VACUUM INTO` backups (18.7GB, integrity-checked) + secondary copy
  (⚠️ same-drive as of 2026-07-04 — see below), restore drill **PASS**, DR runbook
  (`docs/DR_RUNBOOK.md`), 60-day log rotation, `requirements-lock.txt` (186 pins),
  announcement taxonomy tagger (16,963 classified).

### Verification — 29 → 98 pin-to-pin checks
The suite (`common/verify_phases.py`) re-derives every claim from raw tables nightly:
adjusted prices, PIT universe/joins, backfill parity, band invariants, portfolio caps,
scoring reproducibility, membership integrity, pre-registration honesty (scored ⇒ passed
gate; killed ⇒ zero weight), risk-brake re-derivation, PIT strict-`<`, shadow isolation,
cap-lift switch-off. **98/98 green.**

### The frontend (2026-07-03)
React SPA (`web_ui/`): sidebar, 6 pages — Overview (regime+risk hero, log equity curve),
Idea Cards (confidence rings → **thesis drill-down drawer** with exact pillar waterfall),
Risk (brake ladder, concentration), Research & Verdicts (the full ledger), Funds, Events.
Emerald+cyan glass on deep navy, CVD-validated chart palette, framer-motion animation.
Served with basic auth by the stdlib Python server; legacy HTML kept at `/legacy`.

### How to run everything
```powershell
py -3.14 data_extraction\web\serve_dashboard.py   # UI + API -> http://localhost:8765 (admin/micc)
py -3.14 data_extraction\common\verify_phases.py  # 98-check audit
py -3.14 automation\status.py                     # heartbeats, streak x/10, timeout headroom
py -3.14 data_extraction\run_pipeline.py          # manual daily (scheduler does this at 18:30)
py -3.14 automation\backup_db.py --drill          # restore drill (monthly habit)
cd web_ui; npm run build                          # rebuild UI after frontend changes
```

### What honestly remains (all time-gated, none build-gated)
1. **10-green-runs acceptance gate** — streak 0/10; the scheduler proves itself over ~2 weeks.
2. **Event-thesis promotion** — ~mid-2027 (shadow sample accrues daily).
3. **True PEAD** — needs ≥12 PIT quarters (~2028); proxy stays context.
4. **Learning-loop weight proposals** — need ≥30 closed scored trades/pillar (months away).
5. **Live capital** — 12–18 months of paper record + hit-rate/Sharpe/DD thresholds +
   Kite static IP. Explicitly not a 2026 decision.

---

## Progress log

### 2026-07-05 · 01:10 IST — Part 4 Stage 3: survivorship-free PIT universe for SHP — the hole measured, recovery proven

**Why**: Stage 2's verdict — SHP enumeration saw only today's Active list, so delisted
names (the blowups pledge is supposed to catch) were invisible. A pledge test on that
universe is structurally tilted toward "pledge didn't hurt".

**The decisive probe first**: BSE's own API serves the dead. `ListofScripData` exposes
**Delisted (4,612) + Suspended (1,226)** lists with ISINs, and `SHPQNewFormat` serves a
delisted scrip's full filing history — verified on DHFL (19 PIT-timestamped filings up
to its Jun-2021 delisting, Table I parses, grand total 100.0). So recovery = extending
Stage-1 enumeration to the dead lists through the same idempotent, PIT-lag-gated
machinery. Official endpoints only; no archive scraping needed.

**Built**:
- `registry/fetch_bse_scrip_master.py` → `bse_scrip_master` (10,751 scrips incl. dead —
  the ISIN→scrip map that no longer forgets).
- `registry/build_shp_pit_universe.py` → `shp_pit_universe`: quarterly survivorship-free
  spine from the price warehouse (membership: ≥10 trading days in quarter + last trade
  within 21d of quarter-end; funds/ETFs excluded; ISIN resolved as-of via `isin_master`,
  rename-safe), joined to SHP with per-cell status
  (`present` / `missing_active` / `missing_delisted` + reason). 70,503 scrip-quarters,
  42 quarters, idempotent rebuild.
- `events/recover_shp_delisted.py`: bounded, resumable, official-API recovery; outcomes
  in `shp_recovery_log` so re-runs never re-chase known-dead cells. **Smoke-proven**:
  first 2 dead scrips → 43 PIT-usable filings recovered+parsed (one of them **HDFC Ltd**
  — the survivorship hole hides merger-delisted mega-caps, not just blowups), universe
  cells flipped to `present` on rebuild.
- Verify suite **107 → 111** (S10 denominator-is-survivorship-free, S11 no PIT-poison in
  the join, S12 status integrity, S13 recovery-log re-derivability). All green.
- Weekly pipeline: + `bse_scrips` + `shp_universe` phases.

**The corrected coverage matrix (the whole point)**: on the survivorship-free
denominator, fill is **72.9%** overall — and the missing-delisted share is **20.7% of
the 2016 universe, decaying to ~0% today** (textbook adverse survivorship: the early
window is missing exactly its dead names). 1,302 missing-delisted cells sit inside the
top-500 liquidity tiers. Recovery targets: 341 dead scrips with clean BSE mappings
covering 3,283 cells; 914 cells have no BSE scrip (NSE-only names — NSE route is their
fallback), 867 have no ISIN mapping (pre-2016 `isin_master` gaps). Full recovery queued
to run right after the Stage-2 backfill finishes (one fetcher per host). The 5 SHP
signals stay `pending_depth` — no tests run.

### 2026-07-05 · 00:35 IST — Frontend structural upgrade: collapsible sidebar, table search/sort, command palette, symbol profile drawer

Direct follow-on to the polish pass, now explicitly opened up to structural/interaction
changes (not just visual).

- **Collapsible sidebar**: default width trimmed 240px→208px; click the chevron (or
  `Ctrl/Cmd+B`) to fully collapse to a widgets-only full-width view, with a small edge
  tab to bring it back. State persists via `localStorage`.
- **Table search + sort**, opt-in on the shared `Table` component (fully backward
  compatible — existing call sites untouched unless they pass the new props): live
  text search + click-column-to-sort. Wired onto Funds (847-fund scorecard — the
  table that most needed it), Events "Recent events", and the Research verdict ledger
  / IC gate results.
- **Command palette** (`Ctrl/Cmd+K`, also click "Search…" in the sidebar): jump to any
  page or search idea-card symbols by name/company, arrow keys + Enter, no new backend
  calls (reuses the existing `/api/ideas` cache).
- **Symbol profile drawer**: click any symbol (currently wired on Events' Recent-events
  table; palette symbol search opens it too) → one unified view combining
  `/api/asset/{symbol}` (sector, momentum/vol features, fundamentals) with a live
  idea-card summary if one exists and recent events for that symbol — composed
  entirely client-side from **endpoints that already existed**, no backend changes.

**Three real bugs caught by testing in a browser, not just reading the diff** (same
discipline as the polish pass): (1) `deliv_1m` is stored as an already-scaled
percentage (58.6) while the other features are fractions (0.18) — the shared `%`
formatter multiplied it again, rendering "5861.8%" instead of "58.6%"; found by
actually reading the rendered drawer, not assuming the formatter was right. (2)
`prox_52w_high` was mislabeled "distance" when a value of 100% means *at* the high,
not away from it — relabeled to "proximity" to match its actual meaning. (3) Verified
the collapse mechanics (click, keyboard shortcut, persistence-after-reload) each with
a real interaction + screenshot, not just visual inspection of the default state.

Verified with the same Playwright harness as before: dev mode + the real production
build behind basic auth, zero console errors across every page and every new
interaction (search, sort, palette open/search/navigate/symbol-select, drawer
open/close via click/Esc/backdrop).

### 2026-07-04 · 23:50 IST — Frontend visual/motion polish pass (Vercel/Stripe-caliber refinement, same identity/nav/pages)

Scoped per explicit direction: refine the existing emerald+cyan glass-dark identity
(not a redesign), tasteful/subtle animation only, no structural/nav/layout changes,
calibrated to a Vercel/Stripe feel. All 6 pages + shared components touched.

**Design system fixes**: found and unified **4 near-duplicate "eyebrow label" styles**
scattered across files (10px/11px, 0.14em/0.16em/0.2em tracking all doing the same
job) into one `.label` utility. Refined `.glass` with layered depth (inset highlight +
tight + ambient shadow, was one flat shadow) and a shared easing token
(`--ease-out-expo`). Consolidated **animation timings that were previously ad hoc per
component** (0.22s/0.3s/0.8s/0.9s scattered) into `src/lib/motion.js` — one tuned
physics system (`stagger`, `pageTransition`, `springPill`, `springDrawer`) used
everywhere instead of one-off values.

**New states that didn't exist before**: shape-matched **skeleton loaders**
(`StatSkeleton`/`CardGridSkeleton`/`TableSkeleton`/`ChartSkeleton`) replacing a single
generic spinner used identically regardless of what was loading; a real **error state**
(`ErrorState` + retry) — previously a failed fetch just spun the loading indicator
forever, silently, with no way to recover without a page reload.

**Two real bugs caught and fixed by actually testing in a browser, not just reading the
diff**: (1) a botched `Glass`/`motion.div` prop pass-through in Ideas.jsx that would
have silently no-op'd the card press feedback (invalid props on a plain div); (2) a
**sticky table header that looked right in a static screenshot but was structurally
broken** — the table's own `overflow-x-auto` wrapper becomes the nearest CSS scroll
anchor (browser overflow-x/y coupling rule) rather than the actual scrolling `<main>`,
so the header would vanish instead of pinning. Reverted rather than ship non-functional
CSS. Caught by an actual scroll-and-screenshot test, not visual inspection.

**Verification**: full Playwright pass (`npx playwright`, no project run-skill existed
for this yet) — all 6 pages + the thesis drill-down drawer, dev mode AND the real
production build behind basic auth, **zero console errors** throughout. Screenshots
inspected, not just "it loaded."

### 2026-07-04 · 17:30 IST — SHP alpha pre-registration frozen + FPI/DII layer built + Stage 2 (full-depth) started

**Pre-registration (frozen before any test — house rule #1).** A deep evidence-review
brief on "do quarterly SHP changes predict Indian equity returns?" produced 5 candidate
signals, all registered `pending_depth` in `signal_preregistration` with exact
test/window/pass/kill criteria and honest prior verdicts *before touching data*:
`shp_pledge_delta` (prior: survives only as a risk-veto, not a return pillar —
crash-risk literature), `shp_promoter_delta` (borderline → likely context tag),
`shp_fpi_delta` / `shp_dii_delta` (likely fail — priced contemporaneously / herding
modest-to-negative), `shp_composite` (likely fails). **No test has been run**; these
stay `pending_depth` until a separate, explicitly-triggered task.

**FPI/DII data layer (the study needs it, Stage 1 didn't have it).** Table I only had
promoter/public totals — no foreign-vs-domestic institutional split. Added
`shp_institutional_summary` (Table III) + parser in `fetch_shp.py`; BSE cleanly
separates `Foreign Portfolio Investors Cat I/II` from `Institutions (Domestic)`. Parser
self-validates (FPI Cat I+II = Institutions-Foreign subtotal to rounding). New verify
check **S8** (106 total). Pledge% for the veto signal already works from Table I.

**Second fetcher bug caught + fixed.** A targeted `--scrips` test silently ignored its
scope filter in Phase B and grabbed the whole 29k-filing backlog (duplicate BSE load);
killed within 2 min, fixed the scoping so targeted runs stay targeted.

**Part 4 Stage 2 — full-depth backfill + PIT floor.** Empirical floor confirmed from the
data, not assumed: filings-per-quarter cliff-jumps 6 → 58 → **2,226** at qtrid 89
(**March 2016**); pre-2016 filings that carry a timestamp are **retro-uploads** (avg
broadcast lag 2,734 days vs 22 days post-2016 — a 2006 filing broadcast in 2023),
PIT-honest but useless for a quarter-aligned test. So the usable, real-time-filed PIT
window is **Mar 2016 → Mar 2026 = 41 quarters** (was "8 quarters, unpowered"). Full-depth
pass covers Table I + Table III across this window, enforced by a filing-lag
trustworthiness gate (not a blind date cutoff). Coverage audit
(`analysis/shp_coverage_audit.py`) is the actual Stage 2 deliverable — survivorship,
per-segment fill, Table III fill, revision prevalence — before any signal test runs.

### 2026-07-04 · 12:15 IST — All MICC data moved off C:; secondary backup now same-drive (⚠️ DR gap)

House rule enforced: **no MICC data anywhere on C:**, only under `D:\MICC` /
`D:\marketDB`. Found and fixed the one violation: the weekly secondary backup copy
(`C:\MICC_backups\market_*.db`, 18.7 GB) — verified byte-identical (sha256 match) to
the primary backup already on `D:\marketDB\backups\`, then deleted (nothing lost) and
repointed `automation/backup_db.py`'s `SECONDARY_DIR` at `D:\marketDB\backups_secondary\`.
Freed ~18GB on a C: drive that was at 92% full (20GB free → 37GB).
**Honest tradeoff, flagged in `docs/DR_RUNBOOK.md`**: the secondary copy's whole reason
for existing was surviving a **D: drive failure**; now that it's on D: too, that
protection is gone (Scenario 2 in the DR runbook is marked broken) — it now only
guards against accidental deletion/bad pruning of the primary backups dir. Needs a
real off-drive location (external drive/NAS/cloud) to close the gap; `MICC_BACKUP_SECONDARY`
env var makes that a one-line fix whenever one exists.

### 2026-07-04 · 11:00 IST — Part 4 Stage 1: BSE shareholding-pattern acquisition (data-only; no scoring)

**Step-0 route verification first, honest verdicts** ([docs/shp_extraction_routes.md](docs/shp_extraction_routes.md)):
the research report's "announcements category" route is **dead** (BSE announcements has no
SHP category) and `bsesme.com` SHP page is **dead** (error stub) — but both are moot: the
undocumented `api.bseindia.com` JSON layer serves a full SHP endpoint family for
**mainboard + SME in one place** (endpoint names extracted from the site's Angular bundle,
all live-verified). Depth per scrip: quarters back to **2001**; exchange
`filing_date_time` (the PIT anchor) populated from **March 2016**. NSE bulk date-range
route also live (cross-check + what's-new detector).

**Built (additive only, nothing touches scoring/idea_card per house rule #1):**
- `events/shp_schema.py` → `shp_filing` / `shp_category_summary` / `shp_named_holder`
  (Stage 1b). PIT rule enforced in schema + code: `pit_date` = broadcast of **the version
  stored** (a revised filing's PIT is its revision time, not the original filing time).
  Revisions are new rows chained via `is_revision_of`; a partial unique index guarantees
  one current version per scrip-quarter. Raw XBRL on disk (`data_storage/raw/shp/`), not blobs.
- `events/fetch_shp.py` — idempotent sweeper: enumerate (also the weekly new/revision
  detector) → raw XBRL + sha256 → Table I parse. Budget-boxed (`--budget-min`), throttled,
  ntfy summary (`--notify`). Caught in smoke test: BSE lists refiled quarters as TWO
  'New' rows — versions are processed in broadcast-time order so the latest wins.
- Weekly phase wired into `run_pipeline.py --weekly` (`--quarters 8 --budget-min 80`).
- **Verify suite 98 → 105**: PIT sanity, one-current-version, revision-chain + hash-change,
  grand-total ≈100% parse invariant, mainboard/SME coverage, **cross-source promoter-%
  vs the NSE fetcher (8/8 within 1pp)**, revised-after-original. All green.

**Stage 1 backfill launched** (detached): full 4,913-scrip universe (497 SME), last 8
quarters parsed, full 2016→ filing index. Runs ~8–10h; weekly job keeps it current after.
Stages 2–4 (pre-2016 backfill with estimated-PIT policy, delisted names, named holders)
deferred — same gate pattern as Parts 1–3. **No scoring integration** until a
pre-registered walk-forward test earns it.

### 2026-07-03 · 23:00 IST — New React frontend (glassy dark, 6 pages) replaces the single-page HTML

Rebuilt the UI as a proper app: **Vite + React + Tailwind SPA** (`web_ui/`) served by the
same authenticated Python server at `http://localhost:8765` (login `admin`/`micc`).
- **Sidebar, 6 pages**: Overview (regime+risk hero, animated equity curve) · Idea Cards
  (glass cards, confidence rings, **click → thesis drill-down** with pillar-contribution
  chart, price-band visual, context tags) · Risk (brake ladder, sector concentration) ·
  Research & Verdicts (the full ledger, IC gates, CPCV results, exit calibration, Friday
  review, weight versions) · Funds · Events & Smart Money (shadow scoreboard, taxonomy).
- **Design**: emerald+cyan glass on deep navy; chart palette validated for CVD/contrast
  (dataviz six-checks). Framer-motion page transitions, count-ups, animated nav.
- Old dashboard preserved at `/legacy`. All data comes live from `/api/*`
  (7 new endpoints: best/risk/review/verdicts/events/health/sectors).
- **Run it**: `py -3.14 data_extraction\web\serve_dashboard.py` → open `localhost:8765`.
  Rebuild UI after changes: `cd web_ui && npm run build` (Node 24 installed).

### 2026-07-03 · 21:15 IST — Value re-backtest DONE (FAIL, cap stays) — Parts 1–3 fully closed

The last big open item is answered. **Value/quality re-backtest on the extended PIT
history (131 months, 2015→2026): FAIL** — `value_ep` IC +0.005 (t=0.48),
`quality_margin` −0.003 (t=−0.26), `quality_growth` +0.001 (t=0.12) — essentially zero
cross-sectional predictive power **even with the survivorship tailwind** of a
current-survivor universe (~40% historical coverage). Pre-registered verdict:
**the ≤70 confidence cap stays**, now backed by evidence rather than just prudence.
Cap-lift plumbing exists (`--approve-cap-lift`) but has nothing to approve.

Also built: **announcement taxonomy tagger** (16,963 announcements → 13 deterministic
classes, 26% residual for a future LLM layer) — the last optional Part 3 module.
Both wired into the pipeline (daily `ann_tags`, weekly `value_gate` re-run as depth grows).

**Everything remaining is now time-gated, not build-gated:** 10-green-runs streak (0/10,
first full scheduled run tonight), event-thesis promotion (~mid-2027), true PEAD (~2028),
weight proposals (needs ≥30 closed scored trades/pillar), live capital (12–18mo paper).

### 2026-07-03 · 19:30 IST — Parts 1–3 built; hardening sweep done; 98/98 verified

**Where the system stands right now**
- **Idea desk live**: 46 idea cards (₹1cr book, ₹70.9L deployed), ATR bands (stop ≤10%),
  7-pillar auditable confidence (v2.0), portfolio caps, risk meta-engine (DD/streak brakes,
  currently mult ×1.0, DD 3.9%, +₹4.67L cum R-pnl on 540 closed trades).
- **Verdict-driven research**: every challenger pre-registered; regime spine NO-SHIP
  (1.42 vs 1.53), amihud/rs-sector failed IC gates, ridge & LightGBM KILLED under CPCV
  (0.61/0.80 vs champion 1.00). **Only insider cluster buys earned weight** (+2.97% 21d AR,
  t=3.67). Exit-band study on our own 540 trades: whipsaw falsified (1%), KEEP bands.
- **Self-governing**: Friday loop (monitor-only, 0 proposals — sample gates hold),
  weekly integrity-checked backups (18.7GB, restore drill PASS) + secondary copy on C:,
  quarterly auto-gated re-calibrations, failure alerts via ntfy
  (topic `micc-alerts-iy1e2gza3p` — subscribe in the ntfy app), runtime-headroom monitor.
- **Fundamentals depth staged**: 12yr screener history PIT-tagged (FY-end+60d, flagged
  estimated), 356 symbols cap-lift-eligible — **cap stays ON** until the value re-backtest clears.
- **NIFTY 50 named history**: real niftyindices data 2008→2025 (conf 1.0) + Wikipedia-bridged
  Sep-2025 reshuffle to present (conf 0.95, 96% validated vs official).

**Fixed today (hardening sweep):** ntfy failure alerts wired + tested · secondary backup on
C: (quick_check ok) · quarterly auto-gates for exit/ML re-runs · log rotation (60d) ·
`requirements-lock.txt` (186 pins) · DR runbook (`docs/DR_RUNBOOK.md`) · dashboard risk-state +
weekly-review + context-tag + weight-evolution panels · 6 tight phase timeouts raised ·
NIFTY 50 vendor-lag gap bridged.

**Open items (honest):**
1. **Value/quality re-backtest on extended PIT history** → the only path to lifting the ≤70
   confidence cap. Biggest remaining job (next session).
2. **10-green-runs acceptance gate**: streak **0/10** — tonight's daily and Friday's weekly
   are the first runs exercising everything under the scheduler.
3. Time-gated: event-thesis promotion (~mid-2027), true PEAD (needs ≥12 qtrs, ~2028),
   learning-loop weight proposals (needs ≥30 closed scored trades/pillar), live capital
   (12–18mo paper record + Kite static IP).
4. Consciously closed — do not reopen without new evidence: spine/amihud/rs-sector/ML as
   scored signals, F&O signals, calendar effects, sector tail coverage (~60% by design).

---

Built on a clean NSE/BSE + macro **data-extraction** base. Two top-level folders:

```
MICC/
├── data_extraction/     # all the fetcher/extractor scripts
│   ├── market/          # NSE prices, F&O, delivery, greeks, indices
│   ├── macro/           # FRED (US + India), World Bank, RBI, G-Sec
│   ├── funds/           # mutual-fund NAVs
│   ├── events/          # corporate announcements/actions, insider, fundamentals
│   ├── registry/        # stock/BSE registry, tradable universe
│   ├── trends/          # Google Trends
│   ├── common/          # marketdb query API, db health, optimize, debug
│   ├── logs/            # per-script log files
│   ├── run_pipeline.py  # daily orchestrator
│   └── requirements.txt
└── data_storage/        # the data itself
    ├── raw/             # bhavcopy zips, XBRL results, BSE, indices, CA (2005->)
    ├── parquet/         # daily/bse_daily parquet
    ├── duckdb/          # duckdb warehouse
    ├── market_warehouse/
    ├── fiidii/  paper/
```

> The live SQLite DB + per-symbol parquet that scripts read/write still live at
> `D:\marketDB\` (hardcoded in the scripts). `data_storage/` holds the raw archival
> data. These can be consolidated later if you want a single self-contained tree.

## Requirements

Install into the **Python 3.14** interpreter (it has `nselib`, `fredapi`, `nsefin`):

```powershell
py -3.14 -m pip install -r data_extraction\requirements.txt
```

⚠️ **Interpreter matters.** `nselib` and `fredapi` are installed only under Python
3.14 on this machine. Running a script with plain `py` may select 3.13 and fail with
`ModuleNotFoundError`. Always launch with **`py -3.14`** (or use `run.bat`).

## Run

```powershell
cd data_extraction
py -3.14 run_pipeline.py            # full daily extraction
py -3.14 run_pipeline.py --check    # DB health check only
py -3.14 run_pipeline.py --weekly   # + fundamentals, corporate actions, registries
```

Or run any single extractor directly, e.g.:

```powershell
py -3.14 data_extraction\macro\update_macro_us.py --daily
py -3.14 data_extraction\market\update_delivery.py
py -3.14 data_extraction\market\fetch_nse_data.py --fii
```

## Data coverage & deep backfill

The live DB (`D:\marketDB\db\market.db`) has been deep-backfilled from the local
archive (`data_storage/raw/bhavcopy`, offline, survivorship-free) and online sources.

Every dataset is backfilled to **the earliest its source provides**.

**Equity price / volume**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `stock_data` (OHLCV) | ~7.65M | 2005 → 2026 | 4,200 symbols (survivorship-free) |
| `stock_delivery` | ~7.66M | 2005 → 2026 | 4,984 symbols |
| `market_breadth` | 5,304 | 2005 → 2026 | adv/dec, 52w H/L, % >50/200-DMA |
| per-symbol parquet | 37,667 files | 2005 → 2026 | `D:\marketDB\stocks\all` |

**Indices**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `indices_data` (OHLC) | ~88.6k | 1997 → 2026 | 20 NSE/BSE indices |
| `index_valuation` (PE/PB/DivYld) | ~92.9k | 2005 → 2026 | 21 indices (niftyindices) |
| `global_indices_daily` | ~212k | 2000 → 2026 | 35 global symbols/commodities/FX |

**Derivatives**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `fo_data` (F&O) | ~69M | 2005 → 2026 | both legacy + udiff formats |
| `option_greeks_raw` / `gamma_exposure_daily` | ~3.2M | 2007 → 2026 | NIFTY + BANKNIFTY |
| `participant_oi` | ~15k | **2014** → 2026 | NSE disclosure floor |

**Fundamentals & ownership**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `quarterly_income` / `quarterly_balance` | ~21k | — | ~2,340 symbols (yfinance) |
| `quarterly_cashflow` | ~16.8k | **2002** → 2026 | 1,745 symbols (screener.in scraper) |
| `shareholding_history` | ~10k | **2004** → 2026 | promoter/public % |
| `corporate_announcements` | ~13.8k | — | 2,298 symbols |
| `corporate_actions` | ~40.5k | **2005** → 2026 | div/bonus/split/rights classified |
| `insider_trading` | ~280k | **2016** → 2026 | SEBI PIT floor (direct NSE API) |

**Flows / funds / macro / sentiment**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `mf_nav_history` | **~36.9M** | 2006 → 2026 | 37,977 schemes (bulk AMFI) |
| `us_macro_data` (FRED) | ~58k | 1919 → 2026 | |
| `rbi_monetary_data` / `world_bank_macro` / `india_bond_yields` | — | 1960/2000/2011 → 2026 | |
| `bulk_deals` / `block_deals` | ~150k+ | **2006** → 2026 | NSE historicalOR `&csv=true` (uncapped) |
| `short_deals` | — | **2018** → 2026 | NSE short-selling history |
| `fii_dii_data`, `fo_ban`, `google_trends` | recent | forward / blocked | see "source limits" below |

**Derived analytics** (`phase9b`): `symbol_technicals`, `symbol_seasonality`, `symbol_correlations`, `window_stats`, `window_extremes`, `window_regime_stats` — rebuilt across ~3,800 symbols.

**Source limits (cannot go deeper — the data does not exist):** `insider_trading` only from 2016 (SEBI electronic PIT), `participant_oi` only from 2014 (NSE disclosure start), `short_deals` only from 2018. Genuinely **forward-only** (no history at source): `fii_dii_data`, `fo_ban`, and `google_trends` (Google blocks long-range queries). `fetch_deals` + `fetch_fo_ban` are wired into `run_pipeline.py` so they accumulate daily.

### Backfill / scraper tooling (in `data_extraction/`)

All backfills are **idempotent** (`INSERT OR REPLACE`, skip-existing) and have a
generous `busy_timeout` so several can run in parallel (keep it to ~4-5 at once —
SQLite DDL thrashes beyond that).

| Script | → table | Source |
|---|---|---|
| `market/backfill_stocks.py` | `stock_data` | local bhavcopy (legacy+secfull) |
| `market/backfill_delivery.py` | `stock_delivery` | local mto+secfull |
| `market/backfill_indices_hist.py` | `indices_data` | yfinance |
| `market/backfill_fo_data.py --from 2005-01-01` | `fo_data` | NSE archive (udiff + legacy) |
| `market/phase2_greeks_calculator.py --backfill --start 2005-01-01` | greeks/GEX | computed from `fo_data` |
| `market/backfill_participant_oi.py` | `participant_oi` | NSE archive CSVs (2014+) |
| `market/compute_market_breadth.py` | `market_breadth` | computed from `stock_data` |
| `market/fetch_index_valuation.py` | `index_valuation` | niftyindices.com |
| `market/backfill_deals.py` | `bulk_deals`/`block_deals`/`short_deals` | NSE historicalOR `&csv=true` (2006+/2018+) |
| `market/fetch_deals.py` / `fetch_fo_ban.py` | deals / `fo_ban` | NSE daily snapshot (wired into run_pipeline) |
| `events/insider_trading_fetch.py --backfill --from-date 2016-01-01` | `insider_trading` | NSE corporates-pit API |
| `events/backfill_corporate_actions.py --from 2005` | `corporate_actions` | NSE CA bulk API |
| `events/scrape_cashflow.py` | `quarterly_cashflow` | screener.in |
| `macro/fetch_phase1_data.py --bse` | `shareholding_history` | NSE corp-share-holdings |
| `funds/backfill_mf_nav.py --from 2006` | `mf_nav_history` | bulk AMFI NAV history |
| `common/export_parquet.py` | per-symbol parquet | `stock_data` |

## Data expansion roadmap (Tier 1 → 2 → 3)

Additional datasets to extend coverage, by priority. "Backfillable" = deep history
available; "forward" = source serves current day only, so it accumulates over time.

### Tier 1 — ✅ DONE (breadth + valuation backfilled; deals/ban live daily)

| Dataset | Script → table | Source | History |
|---------|----------------|--------|---------|
| Market breadth (adv/dec, 52w H/L, % >50/200 DMA) | `market/compute_market_breadth.py` → `market_breadth` | computed from `stock_data` | ✅ backfillable (2005→) |
| Index PE / PB / Div-Yield | `market/fetch_index_valuation.py` → `index_valuation` | niftyindices.com | ✅ backfillable (2005→) |
| Bulk / Block / Short deals | `market/fetch_deals.py` → `bulk_deals` / `block_deals` / `short_deals` | NSE `snapshot-capital-market-largedeal` | ⏩ forward (run daily) |
| F&O ban list | `market/fetch_fo_ban.py` → `fo_ban` | NSE `fo_secban.csv` | ⏩ forward (run daily) |
| ETF NAV / premium-discount | — | (ETFs mixed into EQ series; needs AMC NAV) | ⏸ deferred |

```powershell
py -3.14 market\compute_market_breadth.py     # breadth (full history)
py -3.14 market\fetch_index_valuation.py       # PE/PB/DivYield (full history)
py -3.14 market\fetch_deals.py                 # bulk/block/short — run daily
py -3.14 market\fetch_fo_ban.py                # F&O ban — run daily
```

### Tier 2 — 4 of 5 done

| Dataset | Script → table | Status |
|---|---|---|
| **News headlines** | `events/fetch_news.py` → `news_headlines` | ✅ 5 RSS feeds (ET/Pulse/MC); daily |
| **IPO data** (GMP/sub/listing) | `events/fetch_ipo.py` → `ipo_data` | ✅ investorgain JSON; daily |
| **India macro** | `macro/update_macro_india_fred.py --backfill` → `india_macro_fred` | ✅ 14 FRED series, 2010→2026 (was 4) |
| **AMFI MF industry flows** | `funds/backfill_amfi_industry.py` → `mf_industry_monthly` | ✅ 87 months 2019→2026 (schemes/folios/funds-mobilized/net-flow/AUM by category) |
| **MF portfolio holdings** | — | ⏸ not done — per-AMC monthly **PDF**, 40+ houses (too fragile) |

> **India high-frequency macro** (GST/PMI/auto/e-way/power) was probed and **dropped** —
> PMI is paywalled (S&P), GST `data.gov.in` API 500s, MOSPI API down; only press-release/PDF
> remains. The clean macro path is the expanded FRED India series above.

### Tier 3 — aggregator-dependent (⚠️ ToS-sensitive)

- Analyst estimates / consensus target prices / rating changes (Trendlyne, Tickertape)
- Brokerage research reports, credit-rating actions (CRISIL/ICRA/CARE)
- Concall transcripts / investor presentations (NLP), NSDL/CDSL fortnightly FPI sector flows, index reconstitution events.

### Extras built (derived / reference data)

| Dataset | Script → table | Notes |
|---|---|---|
| Index constituents + sector | `registry/fetch_index_constituents.py` → `index_constituents` | 21 NIFTY indices, 507 stocks + NSE Industry/sector classification |
| Options PCR / OI analytics | `market/compute_options_analytics.py` → `options_pcr_daily` | daily Put-Call ratio + OI/vol per symbol, 2005→2026 (computed from `fo_data`) |
| Options max-pain | `market/compute_max_pain.py` → `options_max_pain` | NIFTY/BANKNIFTY/FINNIFTY front-expiry max-pain strike, 2005→2026 |
| Annual financials | `events/fetch_annual_financials.py` → `annual_income`/`annual_balance`/`annual_cashflow` | yfinance, complements quarterly_* |
| MF scheme master | `funds/fetch_mf_scheme_master.py` → `mf_scheme_master` | 14,208 schemes → AMC + category (AMFI NAVAll) |
| Earnings calendar | `events/fetch_earnings_calendar.py` → `board_meetings` / `financial_results` | upcoming results/dividend dates + filed results |

### Cross-asset — already covered in `global_indices_daily`

DXY, USDINR/USDJPY/EURUSD/GBPUSD, Gold/Silver/Copper, WTI/Brent/NatGas, Bitcoin,
VIX, India VIX, US 2/10/30Y, + global indices (35 symbols, 2000→2026).

## Analysis & research roadmap (phased)

The warehouse is now broad enough that the bottleneck is **trustworthiness, not coverage**.
The full institutional analysis (19 sections: bias audit, 100+ idea table, signal factory,
factor/event/derivatives/macro/ML blueprints, backtest architecture, dashboards, monetization)
lives in [`MICC_BLUEPRINT.md`](MICC_BLUEPRINT.md); the written-up flagship study (methodology +
results + honest negatives) is in [`RESEARCH.md`](RESEARCH.md). Execution is phased:

| Phase | Goal | Status |
|---|---|---|
| **0 — Audit** | Validate core tables; find lookahead/survivorship in raw + derived | ✅ findings logged + 29/29 pin-to-pin verify (see below) |
| **1 — Clean foundation** | Corporate-action **adjusted prices**, point-in-time universe, fix `financial_results` date bug, ISIN master | ✅ adj prices · PIT universe · results-date · ISIN master |
| **2 — Feature store** | As-of (lagged) momentum / vol / delivery / liquidity / F&O / breadth features | ✅ equity core; F&O studied (weak, overlay-only) |
| **3 — Analytics + first dashboards** | Regime, breadth, screener, MF scorecard | ✅ live signals + self-contained HTML dashboard |
| **4 — Signal research** | 5 ready factors (momentum, low-vol, liquidity, event, derivatives) + delivery/insider/deal overlays | 🔄 momentum+delivery flagship ✅ |
| **5 — Backtest engine** | Walk-forward, transaction costs, capacity, false-discovery control | ✅ full — +inverse-vol/vol-target sizing + capacity curve (~₹100–250cr) |
| **6 — Factor research** | Sector-neutral composite, IC / decay tests, long-short + long-only | ✅ +low-vol 4-factor (Sharpe 1.19); sector-neutral data-limited |
| **7 — Derivatives analytics** | Buildup / rollover / basis / chain / participant positioning | ⬜ |
| **8 — Macro regime** | One composite risk-on/off regime classifier (gate, not signal) | ✅ walk-forward-validated; best config **OOS Sharpe 1.53** (`bt_best`) |
| **9 — ML ranking** | LightGBM cross-sectional ranker on the feature store (purged walk-forward CV) | ✅ tested — **linear beats ML** (OOS Sharpe 1.25 vs 0.76); ML overfits the noise |
| **10 — Productization** | Auth, alerts, polish on the monetizable dashboards | 🔄 MF scorecard + dashboard built (no web/auth layer yet) |
| **11 — Monetization** | MF scorecard / screener / deals / F&O / regime (SEBI-compliant, factual) | 🔄 fund scorecard + signal/dashboard analytics (factual, no advice) |

---

## ▶ REGIME VALIDATION — DONE. PRODUCTION CONFIG LOCKED.

The macro regime gate was walk-forward-validated (`common/backtest_best.py` → `bt_best`):
- **Regime gate beats breadth-only out-of-sample** — WF-adaptive threshold OOS Sharpe **1.56**
  (Calmar 1.37) vs breadth-only **1.34** on the same 2009–2026 window. Validated.
- The specific **≥2/4 threshold did NOT survive** — chosen from past data only, the gate prefers
  **≥1 in 72% of months** (more time in market). So the *engine* is robust; the fixed threshold isn't.
- **Combined best config = inverse-vol weighted top-decile + walk-forward regime gate**:
  **OOS Sharpe 1.53**, Sortino 2.30, MaxDD −18.9%, Calmar 1.26, CAGR 23.9% (`bt_best`, 41.6× equity).
- **vol-target does NOT stack** on the regime gate (1.53→1.40) — the gate already controls risk.
- `generate_signals.py` now reports the live 4-vote regime (latest read: 1/4 → RISK-OFF/cash).

## ▶ MASTER ROADMAP (active) — "trade-it-myself" (60%) + research breadth (40%)

User direction: personal trading system (paper → maybe live later) + research breadth; paper-trading
AND backtest; moderate/pragmatic engineering (no star-schema/staging refactor — overkill for solo);
build sequentially.

| Phase | What | Status |
|---|---|---|
| **1 — Generic strategy engine** | Signal-table backtester + registry; `bt_portfolio_daily`/`bt_trades`/`bt_holdings`/`bt_strategy_metrics`; flagship ported | ✅ done |
| **2 — Strategy library** | + low-vol, short-term-reversal, 52w-breakout; leaderboard | ✅ done (4 strategies) |
| **3 — Paper-trading engine** | Forward simulator: integer shares, real cost model, regime liquidation, live-vs-backtest drift | ✅ done (corr 1.000) |
| **4 — Close data gaps** | Total-return ✅ · PIT-dated fundamentals ✅ · sector map ✅ (63%) | ✅ done |
| **5 — More strategies** | value, quality, dividend, sector-rotation added (8 total); seasonality ⬜ | ✅ 8-strategy library |
| **6 — API + dashboard suite** | stdlib JSON REST API (`/api/*`) + dashboard strategy-leaderboard | ✅ done |
| **7 — Monitoring/governance** | health-check: freshness, data-quality, regime-flip, strategy health | ✅ done (`monitor.py`) |
| **8 — Live trading** *(gated)* | OMS + risk engine + broker interface; **LiveBroker disabled** (paper-safe) | ✅ skeleton; live gated |

**Phase 1/2 — `common/strategy_engine.py`** (generic engine + registry). A strategy is a
function(panel)→`[rebal_date, symbol, weight]`; the engine applies the macro regime gate + costs and
writes standard tables. Leaderboard (net, regime-gated, full period):

| strategy | CAGR | Sharpe | Sortino | MaxDD | Calmar | months |
|---|---|---|---|---|---|---|
| value_earnings_yield* | 28.4% | 1.57 | 4.53 | −14.4% | 1.97 | **49** ⚠ |
| momentum_delivery_lowvol | 17.6% | **1.46** | 2.06 | −16.5% | 1.07 | 245 ✅ |
| quality_roe* | 18.7% | 1.30 | 2.43 | −9.4% | 1.98 | **40** ⚠ |
| dividend_yield | 15.1% | 0.92 | 1.35 | −38.8% | 0.39 | 245 |
| sector_rotation | 13.0% | 0.87 | 1.17 | −44.6% | 0.29 | 245 |
| low_volatility | 8.3% | 0.83 | 1.12 | −20.8% | 0.40 | 245 |
| high52_breakout | 11.0% | 0.82 | 1.22 | −31.0% | 0.35 | 245 |
| short_term_reversal | −4.9% | −0.12 | −0.14 | −87.5% | −0.06 | 245 (fails — correctly) |

*\*Value/quality use PIT fundamentals (`fundamentals_features`, as-of `pit_date` — no lookahead) but the
fundamental data only starts 2021, so their backtests are **short (~3–4 yr) in a strong bull market** —
promising, **not** proven. Momentum (20-yr, walk-forward-validated) remains the only proven strategy.
Deeper fundamental history is the binding data constraint.*

```powershell
py -3.14 common\strategy_engine.py            # run all strategies -> leaderboard + bt_* tables
py -3.14 common\strategy_engine.py --list      # list registered strategies
```

**Phase 3 — `execution/paper_trader.py`** (forward paper-trading simulator → `paper_nav` /
`paper_positions` / `paper_trades`). Stateful virtual portfolio: **integer shares + real cash**,
Indian delivery **cost model** (~0.12%/side: STT+exchange+stamp+GST+slippage), **regime-gated
liquidation to cash** (sells everything + pays cost when regime turns off, re-buys when on), and a
**live-vs-backtest drift** check. Flagship full-history: ₹10L → ₹3.20 cr (32×), CAGR 18.4%, Sharpe 1.53,
MaxDD −16.3%, drift corr **1.000** (engine faithful). At 2026-06-25 (regime RISK-OFF) it correctly
holds all cash.

```powershell
py -3.14 execution\paper_trader.py                                   # flagship, full history
py -3.14 execution\paper_trader.py --strategy low_volatility --start 2018-01-01 --capital 1000000
```

**Phase 4 — data gaps:**
- **4a Total-return** (`common/build_adjusted_prices_tr.py` → `stock_data_tr.close_tr`): back-adjusts
  `stock_data_adj` for cash dividends (13,314 applied). Validated: COALINDIA +7.6%/yr div, ITC +2.2%,
  INFY +2.5% — unblocks dividend / total-return strategies.
- **4c PIT fundamentals** (`events/build_fundamentals_pit.py` → `fundamentals_pit`): attaches a
  point-in-time `pit_date` to every fundamental record (real filing date from `financial_results`
  where available — 1,988 — else period-end + SEBI lag of 45d quarterly / 60d annual; 71,436 rows).
  Backtests must filter `pit_date <= as_of` to avoid lookahead → unblocks value/quality factors.
- **4b Sector map** (`registry/build_sector_map.py` → `dim_sector`): NSE industry (507) + yfinance for
  the rest of the liquid universe, normalized to ~12 common sectors. Resumable/incremental (commits in
  batches). Long-running yfinance fetch.

```powershell
py -3.14 common\build_adjusted_prices_tr.py    # total-return series -> stock_data_tr
py -3.14 events\build_fundamentals_pit.py       # PIT dates -> fundamentals_pit
py -3.14 registry\build_sector_map.py           # sector map -> dim_sector (resumable)
```

Earlier milestone — **regime validation** (`backtest_best.py` → `bt_best`): WF-adaptive regime gate
OOS Sharpe 1.56 vs breadth-only 1.34; combined best (inverse-vol + WF-regime) **OOS Sharpe 1.53**.
Verify anytime with `py -3.14 common/verify_phases.py` (expect 29/29).

---

**Phase 1 — adjusted-price layer** (`data_extraction/common/build_adjusted_prices.py` → `stock_data_adj`):
back-adjusts OHLCV for SPLIT + BONUS so momentum/breakout/event signals aren't poisoned by
price cliffs. Per-event **cliff-verification guard** only applies a factor when the raw close
actually shows the drop — names already adjusted at source (e.g. DBEIL) are skipped to avoid
manufacturing fake cliffs. Last run: 1,130 events applied, 41 skipped (already-adjusted),
128 unverifiable; **1.31 M rows adjusted** of 7.65 M. Known v1 limitations: **dividends**
(price-only momentum doesn't need them) and **RIGHTS** (need subscription price, not stored)
are not yet adjusted — documented for a future total-return series.

**Phase 1 — point-in-time universe** (`data_extraction/registry/build_pit_universe.py` → `pit_universe`):
survivorship-free monthly liquid-universe membership. For each month-end it ranks symbols by
trailing-63-day median turnover (raw close×volume) and flags `top100/250/500` + a ≥₹1cr `liquid`
cut, using **only** data up to that date. **ETFs/funds are excluded** (ISIN prefix INF vs equity
INE, + symbol-pattern fallback; 4,200→3,929 equity symbols) because NAV-creep games momentum /
52w-high / delivery. ~257 months (2005→2026); universe grows backward-to-forward — the signature
of a delisting-inclusive universe. Filter every cross-sectional study through this table.

**Phase 1 — results-date fix** (`events/fetch_earnings_calendar.py`): `broadcast_date` was being
truncated by a `[:10]` slice on NSE's `'25-Jun-2026 16:39:17'` (date+time) string, dropping the
last year digit (`25-Jun-202`). `_iso()` now strips the time component and never emits a partial
date; the garbage-keyed rows were cleared and re-fetched (clean ISO `2025-01-07 → 2026-06-25`).

**Phase 0 — audit finding (lookahead guardrail):** the derived `window_*` and `symbol_*` tables
(`window_extremes`, `window_stats`, `window_regime_stats`, `symbol_technicals`, `symbol_seasonality`,
`symbol_correlations`, `symbol_series_stats`) are **full-sample descriptive snapshots** — each row is
computed over the *entire* history under a single `computed_date`. They are fine for dashboards and
current-state screening but **must NOT be used as point-in-time features in any backtest** (they leak
the future into every historical date). Build as-of features fresh in Phase 2 instead.

**Phase 1 — ISIN master** (`registry/build_isin_master.py` → `isin_master`, `isin_renames`):
maps the stable ISIN to its NSE symbol(s) so a renamed company stays one continuous entity.
Built from ISIN-bearing legacy bhavcopy (2011–2019, monthly-sampled) + current `EQUITY_L.csv`.
3,419 ISINs / 3,382 symbols / 2,394 active, with **276 renames** caught (e.g.
`INE200A01026` → AREVAT&D→ALSTOMT&D→GET&D→GVT&D). Key price series on ISIN, not symbol, to
survive ticker changes. Known v1 gap: pre-2011 and 2020-only renames (no ISIN in those raw files).

**Phase 2 — feature store** (`common/build_feature_store.py` → `features_monthly`): as-of,
point-in-time cross-sectional panel sampled at the 257 monthly rebalance dates (358,127 rows /
4,115 symbols, 2005→2026). Built on `stock_data_adj`, filtered through `pit_universe`. Features:
momentum (`ret_1m/3m/6m/12m`, `mom_12_1`, `mom_6_1`), vol (`vol_3m/6m`), trend (`dist_sma50/200`,
`above_200`, `prox_52w_high`), liquidity (`amihud`, `adv_rank`, `med_turnover`), delivery
(`deliv_1m/3m`, `deliv_trend`). Forward returns are stored ONLY as `fwd_ret_1m`/`fwd_ret_3m`
**labels** (never features). F&O / breadth features are a Phase 2b follow-on.

Self-validation = mean cross-sectional **rank-IC vs forward return** (top500 universe). Every sign
matches theory, magnitudes are realistic (not lookahead-inflated), confirming the adjusted-price +
PIT-universe foundation is clean:

| feature | IC vs 1m | %+ months | IC vs 3m |
|---|---|---|---|
| prox_52w_high | +0.051 | 61% | **+0.090** |
| deliv_1m | +0.045 | 63% | +0.065 |
| mom_12_1 | +0.041 | 65% | +0.052 |
| dist_sma200 | +0.037 | 62% | +0.065 |
| vol_3m | **−0.051** | 40% | −0.072 |
| amihud | −0.023 | 39% | −0.022 |

**Phase 4/5 — flagship backtest** (`common/backtest_momentum.py` → `bt_equity`, `bt_metrics`):
survivorship-free, cost- and regime-aware monthly backtest of a composite signal
(mean percentile-rank of `mom_12_1` + `prox_52w_high` + `deliv_1m`) on the top500 PIT universe,
adjusted-price realized returns, 30 bps/side turnover cost, **equity-only universe (ETFs/funds
excluded)**. Decile spread is **monotonic** (+1.65%/mo gross D10−D1). Headline (net, 2005→2026):

| Strategy | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| **LongOnly D10 + breadth-regime gate** | 15.7% | 13.9% | **1.12** | **−17.8%** | 0.88 |
| LongOnly D10 (no gate) | 19.6% | 21.9% | 0.94 | −65.9% | 0.30 |
| Bench (EW top500) | 10.1% | 29.3% | 0.48 | −72.5% | 0.14 |
| LS (D10−D1) | 9.4% | 30.8% | 0.48 | −79.8% | 0.12 |

Key finding: the **breadth regime gate** (trade only when %>200DMA ≥ 50) cuts max drawdown
−65.9% → −17.8% while holding ~16% CAGR. The naive long-short is poor (momentum-crash on the
short leg) — value is in long-only + gate. Honest caveats: ~38%/mo turnover (capacity-bound),
regime threshold not optimized. (Excluding ETFs/funds, which game momentum/52w-high/delivery via
NAV-creep, slightly *improved* every metric — the low-return funds were diluting the top decile.)

**Phase 5 — backtest hardening** (`common/backtest_hardening.py`): the four rigor tests that make
the flagship defensible (reuses the same `load_panel`). Results:
- **Sub-period stability:** gated LongOnly works in every era — 2005–11 Sharpe 0.90, 2012–18 1.17,
  2019–26 1.30 (rising, no decay). Not one lucky decade.
- **Walk-forward OOS (2008–2026):** IC-weighted composite (past-data-only weights) Sharpe 1.17;
  naive equal-weight 1.29 — edge does not depend on weight-fitting.
- **Parameter sensitivity:** Sharpe plateau across top-10/20/30% × regime 40/50/60% (no knife-edge).
- **Significance:** bootstrap Sharpe 90% CI [0.73, 1.59], P(Sharpe>0)=100%; PSR≈100%; Deflated
  Sharpe≈100% (N=21 trials, SR0=0.15) — not a multiple-testing fluke.

Remaining honest gaps: residual survivorship (~1,258 name-months dropped for mid-month delisting
slightly flatters returns), capacity bound (~38%/mo turnover → real impact > 30bps in smaller
top500 names), execution modeled at month-end close, long-only (short leg is dead — momentum crash).

**Pin-to-pin verification** (`common/verify_phases.py`): independent re-derivation of every Phase
1/2/4/5 claim from raw tables — **29/29 checks pass**. Includes manual recomputes (raw == adj/adj_factor
exact; `mom_12_1` & `fwd_ret_1m` recomputed from `stock_data_adj` 5/5; momentum IC +0.0407 reproduces),
survivorship (delisted `A2ZMES` absent from post-2018 universe), top500 cap = 500, clean ISO result
dates, genuine multi-symbol renames, 0 universe leak, and backtest metrics (Sharpe 1.094, MaxDD −18.0%,
17.5× equity) reproduced. Data-quality note: ~12 of the 60 most-recent split/bonus names (e.g. SKYGOLD,
SME/new listings) have daily-data gaps straddling the ex-date — adjustment factor is still applied
correctly (9:1 bonus → ×0.1), but price-continuity can't be price-verified for those few names.

**Phase 3 — live signal generator** (`common/generate_signals.py` → `current_signals`): operationalizes
the flagship into TODAY's actionable output — the latest month-end top-decile portfolio (the names you'd
hold now) with each name's signal components (12-1 momentum, 52w-high proximity, delivery%) and liquidity,
plus the **live breadth regime gate** (invest vs cash). Latest run (as-of 2026-06-25): regime RISK-OFF
(%>200DMA = 45.1 < 50 → gate to cash); 46-name top-decile book led by ANANDRATHI, NYKAA, FEDERALBNK,
LAURUSLABS, TORNTPHARM. Research output only — not investment advice.

**Phase 6 — multi-factor** (`common/backtest_multifactor.py` → `bt_multifactor`): adds the low-vol
factor (IC +0.058) to the composite. The **4-factor gated book improves risk-adjusted return** —
Sharpe 1.12→**1.19**, Sortino 1.13→1.26, MaxDD −17.8%→**−14.9%**, Calmar 0.88→0.91 (CAGR 13.6% vs
15.7% — the low-vol trade-off). Sector-neutralization *lowered* Sharpe to 1.02 and is **not used**:
sector data is a snapshot covering only ~49% of historical rows. **Phase 2b — F&O study**
(`common/fno_feature_study.py`): PCR / futures-OI features are weak cross-sectionally (|IC|<0.02,
8% coverage; crowding −0.056 but size-confounded) → confirmation overlay only, not a core factor.

**Advanced layer (Phases 8/9 + execution realism):**
- **Phase 9 ML** (`common/ml_ranker.py` → `bt_ml_ranker`): LightGBM learning-to-rank on all 19
  features, purged+embargoed walk-forward CV. **Linear composite beats ML** (OOS Sharpe 1.25 vs 0.76;
  OOS rank-IC +0.082 vs +0.016) — monthly cross-sectional returns are too noisy for the tree model to
  generalize; the transparent rank-composite wins. Honest, leakage-controlled proof of "research-first".
- **Phase 5 execution** (`common/backtest_execution.py` → `bt_execution`): inverse-vol weighting +
  a 12%-vol-target overlay lift **Sharpe 1.12→1.18, Sortino→1.60, Calmar→1.17, MaxDD→−14.0%**.
  Square-root market-impact capacity curve: Sharpe holds ~1.0 to ₹100cr, ~0.7 at ₹250cr → **capacity ≈ ₹100–250cr**.
- **Phase 8 macro regime** (`common/backtest_regime.py`): a 4-vote risk-on classifier (breadth + Nifty
  trend + S&P trend + India-VIX-below-median) replaces the single breadth gate and lifts **Sharpe
  1.12→1.43, Sortino→2.00, CAGR→21.9%** (invested 70% vs 46%). The ≥2/4 threshold is one of three
  tested → flagged for walk-forward validation before production.

**Build/run order (clean-layer pipeline):**
```powershell
py -3.14 common\build_adjusted_prices.py              # rebuild stock_data_adj (idempotent)
py -3.14 registry\build_isin_master.py                 # isin_master + isin_renames (needed by universe ETF filter)
py -3.14 registry\build_pit_universe.py                # pit_universe (equity-only, ETFs excluded)
py -3.14 common\build_feature_store.py                 # features_monthly + IC report
py -3.14 common\backtest_momentum.py                   # flagship backtest A + save curves
py -3.14 common\backtest_hardening.py                  # walk-forward + sub-period + DSR rigor
py -3.14 common\backtest_multifactor.py                # 4-factor (+low-vol) B + sector-neutral test
py -3.14 common\fno_feature_study.py                   # F&O cross-sectional signal study
py -3.14 common\ml_ranker.py                           # Phase 9 LightGBM ranker (vs linear, OOS)
py -3.14 common\backtest_execution.py                  # inverse-vol + vol-target + capacity curve
py -3.14 common\backtest_regime.py                     # Phase 8 macro regime gate (in-sample)
py -3.14 common\backtest_best.py                       # WF-validate regime + combined best (bt_best, OOS 1.53)
py -3.14 common\verify_phases.py                       # 29-check pin-to-pin audit of all phases
py -3.14 common\generate_signals.py                    # today's top-decile book + regime -> current_signals
py -3.14 common\recommendations.py                     # stock recos (entry/target/stop) + score elapsed -> recommendations
py -3.14 common\recommendations.py --report             # just the recommendation scorecard
py -3.14 funds\mf_scorecard.py                         # equity-fund risk-adjusted scorecard -> mf_scorecard
py -3.14 common\build_dashboard.py                     # -> MICC_dashboard.html (open in browser)
```

**Products (Phase 10/11):**
- **`common/recommendations.py` → `recommendations`**: the accountability/feedback loop — turns the
  top-conviction picks into trackable **stock recommendations** (entry / target / stop **price band**,
  volatility-scaled, + a **1-month duration**), logs them, then after the duration **evaluates against the
  real price path** (TARGET-hit / STOP-hit / EXPIRED) and keeps a **scorecard** (hit rate, avg return,
  best/worst). Backfills a historical track record so it works immediately. Track record: 525 closed calls,
  49% hit, +0.47%/call — which *already* surfaced an insight: tight vol-stops whipsaw the momentum edge
  (34% stop-hit), so they hurt. That's the model-improvement loop working. Research only, not advice.
- **`common/generate_signals.py` → `current_signals`**: today's top-decile equity book + the live
  4-vote macro regime (invest vs cash).
- **`funds/mf_scorecard.py` → `mf_scorecard`**: 847 equity Growth funds ranked by 3y Sharpe / CAGR /
  max-drawdown / rolling-1y consistency, within category (factual analytics, not advice; NAV ≠ holdings).
- **`common/build_market_intel.py` → `deals_intel`, `fno_intel`**: recent insider cluster-buys +
  bulk-deal accumulation, and futures-buildup quadrant + PCR extremes on the ~210 F&O names.
- **`common/build_dashboard.py` → `MICC_dashboard.html`**: one self-contained interactive page (regime,
  best-strategy equity curve vs benchmark, metrics, today's portfolio, top funds, smart-money, F&O). No server.
- **`web/serve_dashboard.py`**: stdlib (no-Flask) web layer — serves the dashboard behind HTTP Basic
  Auth with a `/refresh` route. `py -3.14 web/serve_dashboard.py` → http://localhost:8765 (set
  `MICC_USER`/`MICC_PASS` env before sharing; defaults admin/micc).

**Phase 6 — REST API** (`web/api.py`, served by `web/serve_dashboard.py` under the same auth):
`/api/regime`, `/api/strategies` (leaderboard), `/api/signals`, `/api/paper` (NAV series), `/api/funds`,
`/api/deals`, `/api/fno`, `/api/asset/{symbol}` (e.g. RELIANCE → sector + live features). Dashboard also
gained the 8-strategy leaderboard section.

**Phase 7 — monitoring** (`common/monitor.py` → `monitoring_log`): one health-check pass — data freshness,
price/adjustment validity, universe size, regime state + flip, flagship Sharpe, paper portfolio, strategy
count, sector coverage → OK / WARN / ALERT. Run daily.

**Phase 8 — execution stack** (`execution/oms.py` → `oms_orders`): `OMS` + `RiskEngine` (position cap 6%,
≤10% ADV liquidity, min-ticket) + `Broker` interface. `PaperBroker` simulates fills; **`LiveBroker` is a
disabled stub** that refuses to trade without API credentials + an explicit enable flag — no accidental
real orders. Paper rebalance into today's portfolio: 46 orders, risk-checked, 95% deployed.

```powershell
py -3.14 web\serve_dashboard.py     # dashboard (/) + JSON API (/api/*) on :8765, auth admin/micc
py -3.14 common\monitor.py           # daily health-check -> monitoring_log
py -3.14 execution\oms.py            # paper OMS rebalance into signal portfolio -> oms_orders
```

**Pipeline wiring:** `run_pipeline.py` now refreshes products daily (signals → intel → dashboard at the
tail of `DAILY_PHASES`) and rebuilds the whole strategy layer weekly (`--weekly`: isin → adjusted prices
→ PIT universe → feature store → backtests → MF scorecard, in dependency order).

## Notes

- `run_pipeline.py` keeps daily resume state in `data_extraction\pipeline_state.json`.
- **FRED key:** the macro scripts read `os.getenv("FRED_API_KEY")`. Set it before running:
  `setx FRED_API_KEY <your_key>` (open a new terminal afterward). The previously
  hardcoded key was removed from the code and should be rotated.
- Dropped during cleanup (dead/broken): the old `pipeline/` file-watcher framework
  (depended on a missing `agents.shared` package), `backfill_indices.py` (same),
  `fill_parquet_from_delivery.py` (incompatible delivery schema), and the orphaned
  `config.py`.
