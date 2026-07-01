# MICC Data Warehouse — Institutional Analysis Blueprint

> Committee output: Quant Research Head · Portfolio Manager · Market Data Engineer · Risk Manager · Derivatives Strategist · Equity Fundamental Analyst · Macro Strategist · ML Research Scientist · Product/Data Consultant.
>
> **User profile (locked):** Primary = trading/signal research + monetization/resume. Horizon = **position/momentum, 1–6 months**. ML appetite = research-first, ML last. Outputs = Python+SQL, research/backtest designs, dashboard wireframes, strategy doc.
>
> No buy/sell calls. No vague advice. Every idea is mapped to your actual tables/columns. The data is assumed dirty until proven clean.

---

## ASSUMPTIONS STATED (grounded against the live DB, not the inventory text)

These are **verified facts**, not guesses — they override the optimistic inventory where they conflict:

1. **`stock_data` is UNADJUSTED.** Schema = `symbol,date,open,high,low,close,volume`. There is **no `adjusted_close`** and **no adjusted-price table** anywhere in the 57. Corporate-action adjustment must be computed at query time from `corporate_actions`. *This is your single biggest hidden risk.*
2. **`corporate_actions`** = `symbol,date,action_type,ratio,amount,subject` — enough to build split/bonus/dividend adjustment factors, but the linkage is **not yet built or validated**.
3. **`insider_trading`** has both `filing_date` and `report_date` → real point-in-time event studies are possible (use `filing_date` as the knowable date).
4. **`index_constituents` is a single-date snapshot (2026-06-29).** No historical membership. Any index-inclusion / "Nifty 500 universe in 2014" study is **survivorship-poisoned** unless you source point-in-time membership.
5. **Fundamentals are NOT point-in-time.** `annual_*` start 2021, `quarterly_income/balance` start **2024-09** (extremely shallow), yfinance/screener data is **restated** with **no filing-date stamp**. Treat all fundamentals as lookahead-contaminated until you attach result-announcement dates from `financial_results`/`corporate_announcements`.
6. **Greeks/GEX are INDEX-ONLY and COMPUTED.** `option_greeks_raw` covers **NIFTY + BANKNIFTY only**, with an `iv` column that is *your* computed IV, not a vendor mark. Gamma-exposure conclusions inherit every assumption in that IV calc.
7. **`participant_oi` is aggregate** (FII/DII/Pro/Client/TOTAL), not stock-level.
8. **`fii_dii_data` (30 rows) is effectively empty.** Do not build anything on it until backfilled.
9. **`mf_nav_history` is NAV-only.** No holdings. You can rank funds and study flows-vs-performance; you **cannot** do holdings-based factor or overlap analysis.
10. **`shareholding_history` = 174 symbols.** Too thin for a cross-sectional ownership factor; usable only for single-name/event work.

---

# SECTION 1 — EXECUTIVE VERDICT

### What this warehouse can become
A **credible single-operator Indian-market quantitative research platform** specialized in **1–6 month cross-sectional equity momentum, breadth/regime timing, delivery-based accumulation, and F&O positioning** — plus a set of **monetizable dashboards** (regime, breadth, F&O positioning, deals, MF analytics). It is *not* an institutional value-investing engine and should not pretend to be.

### Where edge is actually plausible (ranked)
1. **Cross-sectional momentum / relative-strength at 1–6m on a survivorship-free universe** — your crown jewel. Most retail tools can't do this honestly because they lack delisted names. You can.
2. **Delivery-based accumulation/distribution** (`stock_delivery`, 2005+) — genuinely underexploited; few retail products use 21 years of delivery%.
3. **Breadth/regime timing** as a *filter* (not a standalone alpha) — % above 200DMA, adv/dec thrusts gate when momentum works.
4. **F&O positioning** (futures long/short buildup via price+OI, PCR extremes, rollover) at stock level from `fo_data`.
5. **Event drift** around insider filings, bulk/block deals, corporate actions — modest but real, best as overlays.

### Trading edge: realistic
Plausible **factor-tilt / portfolio edge** (momentum + breadth filter + delivery confirmation), **not** a high-Sharpe timing machine. Expect Sharpe ~0.7–1.2 *gross* on a well-built monthly momentum book; transaction costs and impact in mid/small caps will eat a large chunk. The honest deliverable is a **risk-controlled long/short or long-only-tilt monthly strategy**, not a day-trading signal.

### Investing edge: weak-to-moderate
Capped by non-PIT, shallow fundamentals and thin sector/ownership coverage. You can do **price-and-flow-based investing screens** (momentum + low-vol + liquidity + delivery), but classic **value/quality factor investing is not properly supported** yet.

### Dashboard/product edge: strong
This is where monetization is most realistic *now*. Regime, breadth, F&O positioning, deals, MF ranking, and a survivorship-free screener are all buildable and saleable, with lower compliance risk than signals.

### Genuinely powerful
- 21-year **survivorship-free** daily equity universe (4,200 names).
- 21-year **delivery%** history (4,984 names) — rare.
- 68.9M-row **F&O bhavcopy** with embedded expiry calendar.
- 36.9M-row **MF NAV** history (product-grade for fund analytics).

### Overhyped (in your own inventory)
- **Greeks/GEX** — index-only + computed IV; impressive row count, narrow truth.
- **mf_nav_history's 36.9M rows** — big, but NAV-only ≠ deep analytics.
- **Derived `window_*`/`symbol_*` tables** — convenient, but must be re-audited for baked-in lookahead before trusting.
- **Macro tables** — long history (US from 1919) but monthly/quarterly with release lags; useful only as slow regime context, not signals.

### Missing (blocks institutional credibility)
Adjusted prices (materialized), point-in-time fundamentals with filing dates, **historical** index membership, vendor IV/greeks for stocks, intraday, pledge/borrow data, analyst estimates, MF holdings.

### Build first (the one-sentence answer)
**Build the adjusted-price + corporate-action layer and a survivorship-honest universe-membership table first — nothing else you build is trustworthy until those exist.** Then a momentum + delivery + breadth-filter monthly backtest.

### Ratings (blunt, calibrated to the live DB)
| Dimension | Score | One-line justification |
|---|---|---|
| Data depth | **8/10** | 21yr daily, survivorship-free equity + F&O + delivery is genuinely deep. |
| Data breadth | **8/10** | Equity, F&O, MF, macro, deals, events, ownership — very broad surface. |
| Trading research potential | **7/10** | Excellent for 1–6m momentum/breadth/delivery/F&O; not for intraday/HFT. |
| Long-term investing research | **4.5/10** | Non-PIT, shallow quarterly, thin sector/ownership — the real weak spot. |
| Derivatives research | **6.5/10** | `fo_data` excellent; greeks/GEX index-only & computed; participant data aggregate. |
| ML readiness | **5/10** | Huge raw volume but no feature store, no PIT discipline, leakage landmines. |
| Dashboard/product potential | **8/10** | Tons of dashboard-ready, visually compelling content. |
| Monetization potential | **6/10** | Real products possible; crowded market + compliance + trust barrier. |
| Institutional quality | **4.5/10** | No PIT fundamentals, no historical membership, computed greeks, single-source — impressive for an individual, not yet institution-grade. |

---

# SECTION 2 — DATA QUALITY & BIAS AUDIT

Scores are **institutional usability /10** (would a fund trust it as-is?).

| Dataset group | Strength | Weakness | Major bias risk | Missing-data risk | Lookahead risk | Survivorship risk | Corp-action risk | PIT/timestamp risk | Validation tests required | Score |
|---|---|---|---|---|---|---|---|---|---|---|
| **Equity OHLCV** (`stock_data`) | 21yr, 4,200 names, survivorship-free | **Unadjusted**; thin-name noise | Mid/small illiquidity | Gaps on delisted tails | Low (raw) | **Low (good)** | **HIGH — not adjusted** | Low (daily close) | Build adj factors; cross-check vs index; volume sanity | 6 |
| **Delivery** (`stock_delivery`) | Rare 21yr delivery% | Definition shifts pre-2011; missing days | Reporting changes | Moderate | Low | Low | Inherits price adj | Low | Reconcile qty vs `stock_data.volume`; outlier scan | 7 |
| **Breadth** (`market_breadth`) | Precomputed regime inputs | Depends on universe def used | Universe drift | Low | **Check if forward-filled** | Tied to universe | n/a | Verify as-of construction | Recompute from raw; compare | 5 |
| **Indices** (`indices_data`,`index_valuation`) | Deep, PE/PB/DY | Mixed sources; index methodology changes | Reconstitution | Low | Low | n/a | n/a | Low | Cross-check vendor closes | 7 |
| **Index membership** (`index_constituents`) | Has sector/industry | **Snapshot only (1 date)** | **Severe survivorship** | No history | **HIGH if used historically** | **HIGH** | n/a | **HIGH** | Source PIT membership before any use | 2 |
| **F&O** (`fo_data`) | 68.9M rows, expiry embedded | Legacy+udiff schema mix; 520 names | Contract spec changes | Some early gaps | Low (settle) | Underlying delistings | Strike adj on splits | Low (EOD) | Validate expiry calendar; OI continuity | 6.5 |
| **Greeks/GEX** | Long index series | **Index-only, COMPUTED IV** | Model-assumption bias | NIFTY/BANKNIFTY only | Low | n/a | n/a | EOD | Compare IV vs India VIX; re-derive sample | 4 |
| **PCR/Max-pain** | 418 names PCR | Derived from OI only | OI-stale bias | Low | Low | n/a | n/a | Low | Recompute spot-checks | 6 |
| **Participant OI** | FII/DII/Pro/Client | **Aggregate only**, 2014+ | Category redefinition | Pre-2014 absent | Low | n/a | n/a | EOD | Tie totals to `fo_data` OI | 6 |
| **Deals** (`bulk/block/short`) | Real SEBI/NSE, 2006+ | No counterparty linkage | Selective disclosure | Some gaps | Low (trade date) | Names incl. delisted | Price adj | Low (trade date) | Dedup; price-reconcile | 7 |
| **FII/DII flow** (`fii_dii_*`) | — | **~empty (30/4 rows)** | n/a | **Severe** | n/a | n/a | n/a | n/a | Backfill before use | 1 |
| **Fundamentals** (`annual/quarterly_*`) | Broad symbol count | **Non-PIT, shallow (Q from 2024), restated** | **Restatement+selection** | Many names missing | **HIGH** | Current-listed bias | EPS needs split adj | **HIGH — no filing date** | Attach `financial_results` dates; restatement check | 3 |
| **Shareholding** (`shareholding_history`) | Quarterly promoter/public | **174 names only** | Selection | **Severe coverage** | Moderate (lag) | Thin | n/a | Filing-lag | Expand coverage | 3 |
| **Insider** (`insider_trading`) | 2,407 names, has filing+report date | Noisy (ESOP/pledge mixed in) | Disclosure selection | 2016+ only | **Low if using filing_date** | Incl. delisted | Qty needs adj | **Good (dual dates)** | Classify txn types; dedup | 6.5 |
| **Corp actions** (`corporate_actions`) | 21yr, 2,983 names | Ratio parsing reliability | Ex-date vs record-date | Some misses | Use ex-date carefully | Incl. delisted | **This IS the adj source** | Ex-date accuracy | Parse-audit ratios vs price gaps | 6 |
| **Announcements/results** | Metadata | **Metadata only, no full text**; `financial_results` date format dirty (`01-Feb-202`) | Selection | Sparse | Date-format bug | — | n/a | Dirty dates | Fix date parsing first | 3 |
| **MF NAV** (`mf_nav_history`) | 37,977 schemes, 20yr | **NAV only, no holdings**; dividend-plan NAV resets | Plan duplication | Some gaps | Low | Closed schemes incl.? verify | Div-reinvest resets | Low | Dedup plans; growth-vs-IDCW split | 7 |
| **MF industry/master** | Category/AMC mapping | Snapshot master | — | Low | Low | n/a | n/a | n/a | Map consistency | 6 |
| **Macro** (`us/india/rbi/wb/bond`) | US to 1919 | Monthly/quarterly, **release-lag not modeled** | Revision bias | India thin | **HIGH if aligned naively** | n/a | n/a | **Release lag** | Apply publication lags | 5 |
| **Sentiment** (`news_headlines`,`google_trends`,`ipo_data`) | — | **Tiny/recent only** | Sampling | **Severe** | Recency | n/a | n/a | Live-only | Treat as forward-collect only | 2 |
| **Derived analytics** (`window_*`,`symbol_*`) | Convenient | **Unknown as-of construction** | Possible baked lookahead | — | **AUDIT REQUIRED** | Tied to universe | — | — | Re-derive a sample from raw and diff | 4 |

**The three audit landmines, in order:** (1) unadjusted prices, (2) snapshot-only index membership, (3) non-PIT fundamentals. Fix #1 and #2 before any backtest; quarantine fundamentals until #3 is addressed.

---

# SECTION 3 — ANALYSIS UNIVERSE MAP

Format: **What · Tables · Methods · Best output · Edge · Product value · Difficulty · Priority (P1 highest)**

| # | Bucket | What can be analyzed | Tables | Core methods | Best output | Edge | Product | Diff | Pri |
|---|---|---|---|---|---|---|---|---|---|
| A | Market structure | Liquidity tiers, listing/delisting cohorts, turnover concentration | stock_data, stock_delivery, registries | Cross-sectional turnover buckets | Universe tiers | Low (enabler) | Med | Low | **P1** |
| B | Price-volume | Trend, breakout, volume thrust | stock_data | MA, ATR, vol z-score | Signal features | Med | Med | Low | **P1** |
| C | Delivery/accumulation | Delivery% spikes, sustained accumulation | stock_delivery, stock_data | Delivery z-score, OBV-on-delivery | Accumulation score | **Med-High** | High | Med | **P1** |
| D | Breadth/regime | %>200DMA, adv/dec thrust, new-high/low | market_breadth (rebuild) | Breadth indices, thrust rules | Regime flag | Med (as filter) | High | Low | **P1** |
| E | Index/sector rotation | Relative strength of sectors/indices | indices_data, index_constituents(PIT needed) | RS ranking | Rotation map | Med | High | Med | **P2** |
| F | Relative strength/momentum | 1–6m cross-sectional momentum | stock_data(adj) | Rank returns, skip-month | Momentum book | **High** | High | Med | **P1** |
| G | Volatility/risk | Realized vol, drawdown, regime vol | stock_data, indices_data | Rolling vol, GARCH-lite | Risk overlay | Med | Med | Low | **P2** |
| H | Liquidity/capacity | ADV, impact, capacity ceiling | stock_data, stock_delivery | ADV%, Amihud illiquidity | Capacity tags | High (gatekeeper) | Med | Med | **P1** |
| I | Event studies | Abnormal returns around events | deals, insider, corp_actions, financial_results | CAR/BHAR, market model | Drift charts | Med | Med | Med | **P2** |
| J | Corp action research | Bonus/split/dividend drift | corporate_actions, stock_data | Ex-date event study | Drift table | Low-Med | Med | Med | **P3** |
| K | Earnings reaction | Post-results drift (PEAD) | financial_results, stock_data | Surprise proxy + CAR | PEAD signal | Med (data-limited) | Med | High | **P3** |
| L | Insider research | Cluster-buy drift | insider_trading, stock_data | Net-insider CAR | Insider overlay | Med | High | Med | **P2** |
| M | Bulk/block/short | Smart-money follow-through | bulk/block/short_deals | Net-deal CAR | Deal overlay | Med | High | Med | **P2** |
| N | Futures positioning | Long/short buildup, rollover | fo_data | Price×ΔOI quadrants | Positioning flag | Med | High | Med | **P2** |
| O | Options analytics | PCR, IV, OI walls | fo_data, options_pcr_daily | Aggregations | Chain dashboard | Med | High | Med | **P2** |
| P | Gamma/dealer | GEX regime (index) | gamma_exposure_daily | GEX sign/level | Vol regime flag | Low-Med (computed) | Med | High | **P3** |
| Q | Participant OI | FII vs Client positioning | participant_oi | Net-long ratios | Sentiment gauge | Low-Med | High | Low | **P2** |
| R | Macro regime | Risk-on/off classifier | macro tables, global_indices | Composite z-score | Regime state | Med (slow) | Med | Med | **P3** |
| S | Global correlation | Lead-lag, shock transmission | global_indices_daily, indices_data | Rolling corr, lagged reg | Correlation monitor | Low-Med | Med | Med | **P3** |
| T | Fundamental factors | Value/quality/growth | quarterly/annual_* | Factor z-scores | Factor scores | Low (data-limited) | Med | High | **P4** |
| U | Ownership | Promoter-change drift | shareholding_history | Δ promoter% event | Ownership signal | Low (174 names) | Low | Med | **P4** |
| V | MF analytics | Fund ranking, flows | mf_nav_history, mf_industry, mf_scheme | Rolling return, ratios | Fund product | Med | **High** | Low | **P1** |
| W | IPO analytics | Listing-pop/GMP study | ipo_data (forward) | Collect → study | IPO tracker | Low (no history) | Med | Low | **P4** |
| X | Sentiment/news | Headline/trend signals | news, google_trends | NLP later | Sentiment feed | Low (sparse) | Low | High | **P4** |
| Y | Portfolio construction | Risk-parity, vol-target, sector caps | stock_data, derived | Optimizer, constraints | Backtest engine | High (enabler) | Med | High | **P1** |
| Z | ML/AI | Ranking, regime, vol forecast | feature store | GBM, classifiers | Model layer | Med | Med | High | **P4** |
| AA | Alerts | Threshold/cross alerts | all | Rule engine | Alert center | Med | High | Low | **P2** |
| AB | Dashboards | All views | all | Viz | Product suite | n/a | High | Med | **P1** |
| AC | Data/API products | Curated feeds | curated tables | REST | API | n/a | Med | Med | **P3** |
| AD | Monetization | Bundles | all | Packaging | Revenue | n/a | High | Med | **P2** |

---

# SECTION 4 — MASTER ANALYSIS IDEA TABLE (100+)

Columns: **Idea · Cat · Tables · Logic · Output · Horizon · Diff · Readiness · Edge · Monetize · False-signal risk · Priority/10**. (Cat letters map to Section 3. Diff/Edge/Monetize/Readiness: L/M/H.)

| # | Idea | Cat | Tables | Logic (method) | Output | Horizon | Diff | Ready | Edge | $ | FalseSig | Pri |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 12-1 cross-sectional momentum | F | stock_data(adj) | rank 12m ret skip last 1m; long top decile | rank list | 1–6m | M | H | H | M | M | 10 |
| 2 | Delivery-confirmed momentum | C+F | stock_data,stock_delivery | momentum AND delivery%>rolling mean | filtered list | 1–3m | M | H | H | H | M | 10 |
| 3 | %>200DMA breadth regime gate | D | market_breadth | trade momentum only when breadth>50% & rising | regime flag | regime | L | H | M | H | M | 10 |
| 4 | Adjusted-price layer (enabler) | A | stock_data,corporate_actions | build cumulative adj factor | adj_close table | n/a | M | H | H(enabler) | M | L | 10 |
| 5 | PIT universe membership rebuild | A | bhavcopy,fo_data | derive monthly liquid universe from raw | universe table | n/a | M | H | H(enabler) | M | L | 10 |
| 6 | Liquidity/ADV capacity tags | H | stock_data,stock_delivery | 20d median turnover buckets | tier tags | n/a | L | H | H | M | L | 9 |
| 7 | Amihud illiquidity factor | H | stock_data | mean(|ret|/turnover) | illiq score | 1–6m | M | H | M | M | M | 8 |
| 8 | 52-wk high proximity momentum | F | stock_data | close/52w-high ratio rank | proximity rank | 1–3m | L | H | M | M | M | 8 |
| 9 | Residual (idiosyncratic) momentum | F+S | stock_data,indices_data | beta-adjust returns vs Nifty, rank residual | residual rank | 1–6m | M | H | H | M | M | 9 |
| 10 | Sector relative strength rotation | E | indices_data | rank sector index RS, rotate top-K | sector map | 1–3m | M | M(PIT) | M | H | M | 8 |
| 11 | Delivery spike accumulation | C | stock_delivery | delivery_qty z>2 with price up | watchlist | swing-1m | M | H | H | H | M | 9 |
| 12 | Distribution warning (high vol low delivery) | C | stock_delivery,stock_data | volume z high + delivery% falling | risk flag | swing | M | H | M | M | M | 7 |
| 13 | Volatility-compression breakout | B+G | stock_data | ATR/NR percentile low → breakout watch | breakout list | swing-1m | M | H | M | M | H | 7 |
| 14 | Volume-thrust breakout | B | stock_data | range breakout + volume z>2 | signal | swing | L | H | M | M | H | 7 |
| 15 | Low-vol anomaly portfolio | G | stock_data | long low-realized-vol decile | portfolio | 3–6m | M | H | M | M | L | 8 |
| 16 | Beta-managed momentum | F+G | stock_data,indices_data | scale momentum by inverse beta | weighted book | 1–6m | M | H | M | L | M | 7 |
| 17 | Breadth-thrust entry (Zweig-style) | D | market_breadth | adv/dec 10d ratio thrust | regime entry | weeks | L | H | M | M | M | 7 |
| 18 | New-high/new-low diffusion | D | stock_data,market_breadth | NH-NL index slope | regime gauge | regime | M | H | M | H | M | 7 |
| 19 | Index valuation extreme reversion | E | index_valuation | PE/PB z-score extremes vs fwd index ret | regime tilt | 3–12m | M | H | M | H | M | 7 |
| 20 | Futures long-buildup screen | N | fo_data | price↑ & OI↑ (front fut) | buildup list | swing-1m | M | H | M | H | M | 8 |
| 21 | Futures short-buildup screen | N | fo_data | price↓ & OI↑ | short list | swing-1m | M | H | M | H | M | 7 |
| 22 | Short-covering detection | N | fo_data | price↑ & OI↓ | reversal flag | swing | M | H | M | M | M | 7 |
| 23 | Rollover analytics (expiry week) | N | fo_data | near→far OI shift %, rollover cost | rollover table | monthly | M | H | M | H | M | 8 |
| 24 | Cost-of-carry / basis | N | fo_data,stock_data | (fut-spot)/spot annualized | basis monitor | swing | M | H | L | M | M | 6 |
| 25 | PCR extreme reversal | O | options_pcr_daily | PCR percentile extremes | contrarian flag | swing | L | H | L-M | H | H | 6 |
| 26 | Max-pain distance to spot | O | options_max_pain,indices_data | (spot-maxpain)/spot into expiry | expiry bias | days | L | H | L | M | H | 5 |
| 27 | OI concentration / walls | O | fo_data | strike OI distribution, top walls | S/R map | swing | M | H | L-M | H | M | 6 |
| 28 | GEX regime (index vol) | P | gamma_exposure_daily | GEX sign → mean-revert vs trend regime | vol regime | days-wk | H | M(computed) | M | M | H | 5 |
| 29 | IV vs realized spread (index) | O+G | option_greeks_raw,indices_data | IV − realized vol | vol-risk premium | wk | M | M | M | M | M | 6 |
| 30 | Participant net-long (Client vs FII) | Q | participant_oi | FII index-fut net long ratio | sentiment | swing-1m | L | H | L-M | H | M | 6 |
| 31 | Insider cluster-buy drift | L | insider_trading,stock_data | ≥N buyers/window → CAR | insider signal | 1–3m | M | H | M | H | M | 8 |
| 32 | Promoter-buy vs ESOP filter | L | insider_trading | classify acquisition type | clean insider feed | 1–3m | M | H | M | H | M | 7 |
| 33 | Bulk-deal accumulation follow | M | bulk_deals,stock_data | net buy value z → forward ret | deal signal | wk-1m | M | H | M | H | M | 7 |
| 34 | Block-deal follow-through | M | block_deals,stock_data | block side → drift | overlay | wk-1m | M | H | M | H | H | 6 |
| 35 | Short-deal pressure / squeeze setup | M | short_deals,stock_data,fo_data | high short + OI context | squeeze watch | swing | M | H | M | M | H | 6 |
| 36 | PEAD post-results drift | K | financial_results,stock_data | event CAR by reaction sign | PEAD signal | 1–3m | H | L(date bug) | M | M | M | 5 |
| 37 | Bonus/split ex-date drift | J | corporate_actions,stock_data | event study around ex-date | drift table | days-wk | M | H | L-M | L | M | 5 |
| 38 | Dividend-capture viability | J | corporate_actions,stock_data | ex-date drop vs dividend | research note | days | L | H | L | L | M | 4 |
| 39 | Sector-neutral momentum | F+E | stock_data,index_constituents(PIT) | demean momentum within sector | neutral book | 1–6m | M | M | M | M | M | 7 |
| 40 | Multi-factor composite (mom+lowvol+illiq+delivery) | Y | stock_data,stock_delivery | z-score blend, rank | composite score | 1–6m | M | H | H | H | M | 9 |
| 41 | Momentum crash protection | F+G | stock_data,market_breadth | cut momentum after bear+high-vol | dynamic book | 1–6m | M | H | M | M | M | 8 |
| 42 | Pairs/cointegration (sector peers) | S | stock_data | rolling coint, z-spread | pair signals | wk-1m | H | H | M | M | H | 6 |
| 43 | Correlation-breakdown alerts | S | stock_data,global_indices | rolling corr regime shift | alert | wk | M | H | L-M | M | M | 5 |
| 44 | USD/INR sensitive baskets | R | global_indices,stock_data | beta to INR, basket build | macro basket | 1–3m | M | H | M | M | M | 6 |
| 45 | Crude-sensitive sector basket | R | global_indices,indices_data | beta to Brent | basket | 1–3m | M | H | M | M | M | 6 |
| 46 | US-yield impact on rate-sensitives | R | macro,indices_data | lagged regression | sensitivity map | 1–3m | M | M | L-M | M | M | 5 |
| 47 | VIX-shock playbook | R+G | global_indices,indices_data | India VIX/global VIX spikes → fwd ret | regime study | days-wk | M | H | M | M | M | 6 |
| 48 | Macro composite regime classifier | R | all macro | z-score state machine | regime state | months | M | M | M | M | M | 6 |
| 49 | MF category-rotation dashboard | V | mf_industry_monthly | net flow & return by category | rotation view | monthly | L | H | L-M | H | L | 7 |
| 50 | MF rolling-return ranking | V | mf_nav_history,mf_scheme | 1/3/5y rolling, percentile | fund ranks | n/a | L | H | M | H | L | 8 |
| 51 | MF risk-adjusted (Sharpe/Sortino/Calmar) | V | mf_nav_history | ratio computation | scorecards | n/a | L | H | M | H | L | 8 |
| 52 | MF rolling-drawdown & recovery | V | mf_nav_history | underwater curves | risk view | n/a | L | H | M | H | L | 7 |
| 53 | SIP-vs-lumpsum backtester | V | mf_nav_history | XIRR sim | calculator | n/a | M | H | L | H | M | 7 |
| 54 | MF flow-vs-performance | V | mf_industry,mf_nav | flows lead/lag returns | study | monthly | M | H | M | M | M | 6 |
| 55 | MF consistency score | V | mf_nav_history | % rolling windows in top quartile | score | n/a | M | H | M | H | L | 7 |
| 56 | NAV-momentum fund tilt | V | mf_nav_history | recent NAV momentum persistence | fund signal | 1–6m | M | H | L-M | M | H | 5 |
| 57 | Drawdown-probability features | G | stock_data,market_breadth | regime+vol features → labels | risk model input | wk | M | H | M | M | M | 6 |
| 58 | Capacity/slippage estimator | H | stock_data,stock_delivery | ADV%, sqrt impact | capacity tool | n/a | M | H | H(enabler) | M | L | 8 |
| 59 | Turnover-aware momentum (cost-adjusted) | F+H | stock_data | net-of-cost rebalance test | net backtest | 1–6m | M | H | H | M | M | 8 |
| 60 | Seasonality by symbol/month | B | symbol_seasonality(audit) | month-of-year mean ret + test | seasonality | n/a | L | M | L | M | H | 4 |
| 61 | Gap-and-go / gap-fade study | B | stock_data | open-gap forward behavior | study | days | M | H | L | L | H | 4 |
| 62 | Trend-quality (R² of price) | B | stock_data | regression R² rank | trend score | 1–3m | L | H | M | M | M | 7 |
| 63 | Volatility-targeted index timing | G+D | indices_data,market_breadth | scale exposure to inv-vol+breadth | overlay | regime | M | H | M | M | M | 7 |
| 64 | Drawdown-control stop framework | Y | stock_data | vol-based trailing stop backtest | rule set | swing-1m | M | H | M | L | M | 6 |
| 65 | Risk-parity sector allocation | Y | indices_data | inverse-vol weights | allocation | monthly | M | H | M | M | M | 6 |
| 66 | Multi-timeframe momentum blend | F | stock_data | blend 3/6/12m ranks | robust rank | 1–6m | M | H | H | M | M | 8 |
| 67 | Acceleration (2nd-derivative momentum) | F | stock_data | Δ momentum rank | early-rotation | 1–3m | M | H | M | M | H | 6 |
| 68 | Relative-volume persistence | B | stock_data,stock_delivery | RVOL streak detection | activity flag | swing | L | H | L-M | M | M | 5 |
| 69 | Liquidity-squeeze early warning | H | stock_data,stock_delivery | turnover collapse z | risk alert | swing | M | H | M | M | M | 6 |
| 70 | F&O ban-prediction (when collected) | N | fo_data,fo_ban | MWPL% proxy from OI | risk flag | days | M | L(fo_ban empty) | M | M | M | 4 |
| 71 | Expiry-week index behavior | O+N | fo_data,indices_data | day-of-expiry-week return profile | playbook | days | M | H | L-M | M | H | 5 |
| 72 | Stock-level options skew (where data) | O | fo_data | CE/PE OI & price skew | skew gauge | swing | H | M | L-M | M | H | 4 |
| 73 | Insider+deal confluence | L+M | insider,bulk/block | both signals agree → stronger CAR | confluence | 1–3m | M | H | M | H | M | 7 |
| 74 | Corporate-action adjusted backtester | A+J | corporate_actions,stock_data | total-return series | clean series | n/a | M | H | H(enabler) | M | L | 9 |
| 75 | Delisting-survival flag | A | registries,stock_data | last-trade detection | quality tag | n/a | L | H | H(enabler) | L | L | 7 |
| 76 | Penny/illiquid exclusion filter | H | stock_data | price/turnover floors | clean universe | n/a | L | H | H(enabler) | L | L | 8 |
| 77 | Mean-reversion (oversold quality) | B | stock_data | RSI/zscore on liquid names only | MR signal | days-wk | M | H | L-M | M | H | 5 |
| 78 | Volatility regime HMM (index) | G | indices_data | 2-3 state HMM on vol | regime label | regime | H | H | M | M | M | 6 |
| 79 | Cross-asset risk-on/off composite | R+S | global_indices | risk asset vs safe-haven z | macro state | wk-mo | M | H | M | M | M | 6 |
| 80 | India-vs-EM relative regime | S | global_indices,indices_data | relative-strength of Nifty vs EM | allocation cue | mo | L | H | L-M | M | M | 5 |
| 81 | Earnings-calendar event-risk overlay | K | board_meetings,financial_results | flag pre-results names | risk overlay | days | L | M(sparse) | L | M | M | 5 |
| 82 | Bulk-deal investor tracking | M | bulk_deals | aggregate by client name | smart-money tracker | n/a | M | H | M | H | M | 6 |
| 83 | Promoter-pledge proxy (when sourced) | U | (missing) | needs new data | — | n/a | — | L | M | M | M | 3 |
| 84 | Shareholding-change drift (174) | U | shareholding_history,stock_data | Δpromoter% event | signal | qtr | M | H(thin) | L-M | L | M | 4 |
| 85 | Factor decay / IC monitor | Y | stock_data,derived | rolling rank-IC of each factor | factor monitor | n/a | M | H | H | M | L | 8 |
| 86 | Regime-conditional factor returns | Y+D | stock_data,market_breadth | factor ret split by regime | research | n/a | M | H | H | M | M | 8 |
| 87 | Turnover-decile return spread | H | stock_data | sort by turnover, fwd ret | liquidity premium | 1–6m | L | H | M | M | M | 6 |
| 88 | Index-inclusion drift (needs PIT) | I | (PIT membership) | event study | study | wk | M | L | M | M | M | 4 |
| 89 | Sector breadth divergence | D+E | stock_data,index_constituents | sector %>50DMA divergence | rotation cue | wk | M | M | M | H | M | 6 |
| 90 | Volatility-of-volatility signal | G | indices_data,option_greeks | vol-of-IV regime | tail flag | wk | H | M | L-M | M | H | 4 |
| 91 | Drawdown-recovery base detection | B | stock_data | base-building pattern post-DD | setup screen | swing-1m | M | H | M | M | H | 6 |
| 92 | Multi-factor MF scorecard product | V | mf_nav,mf_scheme | blend return+risk+consistency | product | n/a | M | H | M | H | L | 8 |
| 93 | Macro-surprise alignment (lagged) | R | macro | release vs market reaction | study | mo | H | M | L | L | H | 4 |
| 94 | Correlation-network clustering | S | stock_data | corr matrix → clusters | risk map | n/a | H | H | M | M | M | 6 |
| 95 | Crowding detection (factor) | Y | stock_data,derived | factor exposure dispersion | risk warning | n/a | H | M | M | M | M | 5 |
| 96 | News-flow event-tagging (forward) | X | news_headlines | NLP tag → event study | feed | wk | H | L(sparse) | L | M | H | 3 |
| 97 | IPO listing-pop study (forward collect) | W | ipo_data | GMP vs listing return | study | days | M | L | L-M | M | M | 4 |
| 98 | Composite "smart-money" index | L+M+Q | insider,deals,participant_oi | blended z-score | sentiment index | wk | H | H | M | H | M | 6 |
| 99 | Full survivorship-honest backtest harness | Y | all clean | the engine itself | platform | n/a | H | H | H(enabler) | M | L | 10 |
| 100 | Strategy-decay / live-tracking monitor | Y | live signals | OOS performance tracking | monitor | n/a | M | H | H | M | L | 8 |
| 101 | Delivery-momentum interaction factor | C+F | stock_delivery,stock_data | momentum × delivery trend | enhanced factor | 1–3m | M | H | H | H | M | 9 |
| 102 | Volatility-scaled position sizing | Y+G | stock_data | inverse-vol weights in book | sizing rule | 1–6m | L | H | M | L | L | 8 |

---

# SECTION 5 — SIGNAL FACTORY

Each family below uses the 18-field template. To keep this usable I give the template once, then specify the **distinguishing fields** per family (the rest follow the defaults).

**Template fields:** Name · Thesis · Tables · Columns · Formula · Frequency · Universe filter · Entry · Exit · Risk filter · Hold · Best regime · Failure regime · Backtest design · Eval metrics · Expected edge · Overfit risk · Example.

**Global defaults (apply unless overridden):**
- **Universe filter:** liquid tier only — 20d median turnover ≥ ₹2cr, price ≥ ₹20, ≥250 trading days listed, exclude T2T/illiquid. *(Built from `stock_data`+`stock_delivery`.)*
- **Risk filter:** skip if name in F&O ban / >15% gap / data gap in last 5d; cap single-name weight; sector cap.
- **Backtest design:** monthly rebalance, walk-forward, **adjusted prices**, costs = 0.20% round-trip + slippage = 0.3×(order/ADV) impact, regime-split (bull/bear/high-vol), rank-IC + decile spread.
- **Eval metrics:** rank-IC, decile long-short spread, Sharpe/Sortino, max DD, turnover, capacity, hit-rate by regime.

### Family 1 — Momentum
- **Thesis:** 1–6m relative strength persists in Indian equities. **Tables:** stock_data(adj). **Formula:** rank `r = close[t-21]/close[t-252]-1`; long top decile. **Freq:** monthly. **Entry:** top-decile rank. **Exit:** drop below top-3-decile. **Hold:** 1–3m. **Best regime:** trending bull, breadth>50%. **Failure:** sharp reversals/momentum crashes (post-crash rebounds). **Expected edge:** rank-IC ~0.03–0.06, L/S Sharpe ~0.7–1.0 gross. **Overfit:** low (well-known, robust). **Example:** Long top-decile 12-1 momentum, sector-capped.

### Family 2 — Trend following
- **Thesis:** persistent single-name trends. **Formula:** price>200DMA AND 50DMA>200DMA AND R²(60d log price)>0.6. **Freq:** weekly. **Exit:** close<50DMA. **Hold:** weeks–months. **Failure:** choppy range markets. **Overfit:** med (parameter-sensitive). 

### Family 3 — Mean reversion
- **Thesis:** short-term oversold bounces in *liquid quality* only. **Formula:** 5d return z<-2 AND price>200DMA AND turnover top-quartile. **Freq:** daily. **Exit:** z>0 or 5 days. **Hold:** days–2wk. **Failure:** trending bear (catches knives). **Overfit:** **high** — guard hard with liquidity + trend filter. 

### Family 4 — Breakout
- **Formula:** close > max(high,55d) AND volume z>2 AND ATR-percentile rising. **Exit:** close<20DMA or −1.5ATR. **Failure:** false breakouts in low-breadth. **Overfit:** high (lookback shopping). 

### Family 5 — Volatility compression
- **Formula:** ATR(14)/close in bottom 10th percentile (252d) → arm; trade direction of subsequent breakout. **Failure:** compression that resolves against trend. **Overfit:** med-high. 

### Family 6 — Volume expansion
- **Tables:** stock_data,stock_delivery. **Formula:** volume z>2.5 AND price up AND delivery%>20d-mean. **Exit:** volume normalizes. **Failure:** news-driven one-day spikes. 

### Family 7 — Delivery spike *(your differentiated edge)*
- **Tables:** stock_delivery,stock_data. **Columns:** delivery_qty, delivery_percent. **Formula:** delivery_qty z(60d)>2 AND delivery_percent>40 AND close>20DMA. **Freq:** daily→swing. **Hold:** 2wk–1m. **Best regime:** accumulation phases, mid-caps. **Failure:** illiquid spikes / single block trades — *filter via deals table*. **Expected edge:** med-high, under-arbitraged. **Overfit:** med. 

### Family 8 — Accumulation/distribution
- **Formula:** OBV computed on *delivery* volume (not total) rising 20d AND price flat/up = accumulation; falling delivery-OBV + rising price = distribution warning. **Hold:** 1–3m. 

### Family 9 — Breadth thrust
- **Tables:** market_breadth. **Formula:** 10d adv/dec ratio crosses >2 from <1 (Zweig). **Freq:** daily. **Use:** regime *gate*, not single-name. **Failure:** rare; whipsaw in micro-rallies. **Overfit:** low. 

### Family 10 — Breadth deterioration
- **Formula:** %>200DMA falls below 40 AND new-lows>new-highs 5 consecutive days → de-risk. **Use:** exposure cut. 

### Family 11 — Sector rotation
- **Tables:** indices_data (+PIT constituents). **Formula:** rank sector indices by 3m RS; rotate to top-K, exit bottom-K. **Freq:** monthly. **Failure:** rotation reversals at turns. 

### Family 12 — Relative strength
- **Formula:** stock return − sector/Nifty return, rank; long high-RS within strong sectors (double sort). **Hold:** 1–3m. 

### Family 13 — Index valuation extremes
- **Tables:** index_valuation. **Formula:** index PE z-score(5y)>+2 → reduce; <−2 → add (slow). **Freq:** monthly. **Use:** allocation tilt, not timing. 

### Family 14 — Insider buying
- **Tables:** insider_trading,stock_data. **Formula:** within 30d, ≥2 distinct insiders net-buy (exclude ESOP/pledge via `transaction_type`/`category`) → event. **Use filing_date.** **Hold:** 1–3m. **Edge:** CAR positive on cluster buys. **Overfit:** med. 

### Family 15 — Insider selling
- **Formula:** heavy promoter net-sell (value z>2) → caution flag (weak standalone; many benign reasons). **Use:** risk overlay only. 

### Family 16 — Bulk-deal accumulation
- **Tables:** bulk_deals. **Formula:** 20d net buy value z>2, repeat buyers → drift study. **Hold:** wk–1m. 

### Family 17 — Block-deal follow-through
- **Formula:** block trade > X% of ADV; trade direction of buyer side for short drift. **Failure:** blocks are often portfolio reshuffles, not directional. **Overfit:** med-high. 

### Family 18 — Short-selling pressure
- **Tables:** short_deals,fo_data. **Formula:** short volume z high + price weak → continuation; combined with low float/high OI → squeeze setup. 

### Family 19 — Short covering
- **Formula (F&O):** price↑ AND OI↓ on front future. **Hold:** swing. 

### Family 20 — Futures long buildup
- **Tables:** fo_data. **Formula:** front-future price↑ AND open_int↑ AND chg_in_oi>0. **Freq:** daily. **Hold:** swing–1m. 

### Family 21 — Futures short buildup
- **Formula:** price↓ AND OI↑. Mirror of 20. 

### Family 22 — PCR extremes
- **Tables:** options_pcr_daily. **Formula:** PCR percentile(1y) >90 (excess puts→contrarian bullish) / <10 (contrarian bearish). **Failure:** strong trends ignore PCR. **Overfit:** high. 

### Family 23 — Max-pain distance
- **Tables:** options_max_pain,indices_data. **Formula:** (spot−maxpain)/spot into expiry week → pin bias. **Hold:** days. **Failure:** trend overwhelms pin. 

### Family 24 — Gamma squeeze risk
- **Tables:** gamma_exposure_daily. **Formula:** dealer GEX strongly negative + price near large OI strike → instability flag. **Index-only.** **Overfit/model risk:** high. 

### Family 25 — Dealer gamma regime
- **Formula:** GEX>0 → mean-reverting/low-vol regime; GEX<0 → trend/high-vol. **Use:** index vol-regime gate. **Caveat:** computed IV. 

### Family 26 — FII/Client/Pro positioning
- **Tables:** participant_oi. **Formula:** FII index-future net-long ratio z; Client opposite. **Hold:** swing–1m. **Use:** sentiment overlay. 

### Family 27 — Macro risk-on/off
- **Tables:** macro,global_indices. **Formula:** composite z (yields, USD, crude, VIX) → state. **Freq:** weekly. **Use:** slow exposure dial. 

### Family 28 — Global market shock
- **Formula:** overnight global drawdown > X σ → next-day India gap study / de-risk. **Hold:** days. 

### Family 29 — USD/INR impact
- **Formula:** rolling beta of name to USDINR; build importer/exporter baskets. **Hold:** 1–3m. 

### Family 30 — Crude impact
- **Formula:** beta to Brent; OMC/aviation/paint baskets. 

### Family 31 — US yields impact
- **Formula:** lagged regression of rate-sensitive sectors on UST10Y Δ. **Edge:** weak/slow. 

### Family 32 — Earnings reaction (PEAD)
- **Tables:** financial_results,stock_data. **Formula:** 2d post-result CAR sign → 1–3m drift (momentum of surprise). **Blocker:** fix `financial_results` date parsing first; no analyst-estimate surprise (use price-reaction proxy). 

### Family 33 — Corporate-action drift
- **Tables:** corporate_actions. **Formula:** event study around ex-date for bonus/split (liquidity/attention effect). **Edge:** weak. 

### Family 34 — Mutual-fund category rotation
- **Tables:** mf_industry_monthly. **Formula:** category net-flow + return momentum → rotation dashboard. 

### Family 35 — Fund NAV momentum
- **Tables:** mf_nav_history. **Formula:** rank funds by 6–12m NAV return within category; persistence test. **Caveat:** weak edge, strong *product*. 

### Family 36 — IPO listing risk
- **Tables:** ipo_data (forward). **Formula:** GMP/subscription vs listing return (collect first). 

### Family 37 — Correlation breakdown
- **Formula:** rolling 60d corr regime-shift detection between pairs/assets → diversification alert. 

### Family 38 — Pair trading
- **Formula:** cointegrated sector peers, z-spread entry ±2, exit 0. **Overfit:** high — strict OOS + multiple-testing control. 

### Family 39 — Liquidity squeeze
- **Tables:** stock_data,stock_delivery. **Formula:** turnover z< −2 streak → exit/avoid (capacity risk). 

### Family 40 — Drawdown risk
- **Formula:** features = regime + vol + breadth + name DD depth → label P(further −X% in 20d). Risk-overlay, not entry. 

---

# SECTION 6 — FACTOR RESEARCH BLUEPRINT (Indian equities)

**Common protocol for every factor:** monthly rebalance · liquid universe (Section 5 default) · **sector-neutralize** (needs PIT sector — interim: GICS-proxy from current `index_constituents`, flagged as approximate) · winsorize at 1/99 pct · z-score standardize · **rank-IC + decile L/S** · Newey-West t-stats · factor-decay (IC vs horizon 1–12m) · long-only top-quintile AND market-neutral L/S versions · cost-adjusted.

| Factor class | Definition | Tables | Formula | Rebal | Neutralize | Winsor/Std | Expected weakness | Backtest | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Value** | Cheapness | index_valuation (sector px); quarterly_* (thin) | E/P, B/P from financials | M/Q | sector | 1/99,z | **Non-PIT, shallow → unreliable now** | rank-IC | ❌ blocked (PIT) |
| **Quality** | Profitability/stability | annual/quarterly_income,balance | ROE, accruals, earnings stability | Q | sector | 1/99,z | Restated data, 2021+ only | L/S | ❌ blocked |
| **Growth** | Trend in fundamentals | quarterly_income | YoY rev/EPS growth | Q | sector | 1/99,z | Q data from 2024 only | L/S | ❌ too shallow |
| **Momentum** | Price persistence | stock_data(adj) | 12-1, 6-1, residual | M | sector | 1/99,z | Crashes at reversals | rank-IC,decile | ✅ ready |
| **Low volatility** | Risk anomaly | stock_data | inverse 120d realized vol | M | sector | 1/99,z | Crowding; rate-sensitive | L/S | ✅ ready |
| **Liquidity** | Illiquidity premium | stock_data,stock_delivery | Amihud, turnover | M | sector,size | 1/99,z | Capacity-limited, hard to trade | decile | ✅ ready |
| **Ownership** | Promoter conviction | shareholding_history | Δpromoter%, promoter level | Q | sector | 1/99,z | **174 names only** | event | ⚠️ thin |
| **Event** | Insider/deal flow | insider_trading,bulk_deals | net-insider z, net-deal z | M | sector | 1/99,z | Sparse, noisy | L/S overlay | ✅ ready |
| **Derivatives** | Positioning | fo_data,options_pcr_daily | Δfut-OI sign, PCR z, basis | M/W | size | 1/99,z | F&O names only (~190) | decile | ✅ (F&O univ) |
| **Macro-sensitive** | Beta baskets | global_indices,stock_data | β to USDINR/Brent/UST | M | — | z | Unstable betas | basket | ⚠️ regime-dependent |

**Verdict:** Of 10 factor classes, **5 are genuinely ready** (momentum, low-vol, liquidity, event, derivatives) — and all 5 are *price/flow-based*, which is exactly your data's strength. The four fundamental classes (value/quality/growth/ownership) are **data-blocked** and should wait for PIT fundamentals. Build a **composite of the 5 ready factors** as your flagship.

---

# SECTION 7 — EVENT STUDY FRAMEWORK

**Universal design:** Event date = **knowable date** (filing_date for insider; trade date for deals; ex-date for CA; result-filing date for earnings). Estimation window = [−250, −30]; event window = [−5, +60] (drift). Abnormal return = **market-model** (β vs Nifty 500 proxy) AND **size/sector-matched control portfolio** (more robust in India). Benchmark = liquid sector peer median. Controls: liquidity tier, market-cap bucket, concurrent-event exclusion. **Liquidity filter mandatory** (drift in illiquids is an artifact). Stat tests: cross-sectional t-test on CAAR, **sign test**, bootstrap CI, BHAR for long horizons. Charts: CAAR ± CI, by-quartile fan, by-regime.

| Event | Event date | Window | AR method | Key trap | Likely edge? |
|---|---|---|---|---|---|
| Insider cluster-buy | filing_date | [−5,+60] | mkt-model + control | Mixing ESOP/pledge → classify first | **Yes (modest)** |
| Bulk deals | trade date | [−2,+20] | control portfolio | Deal already moved price (info in t0) | Maybe |
| Block deals | trade date | [−2,+20] | control | Portfolio reshuffle ≠ directional | Weak |
| Short deals | trade date | [−1,+10] | control | Squeeze vs continuation ambiguity | Maybe |
| Corp actions (bonus/split) | ex-date | [−10,+20] | mkt-model | Need adjusted prices to even measure | Weak |
| Dividend | ex-date | [−5,+5] | mkt-model | Tax/clientele noise | Weak |
| Results (PEAD) | filing date | [0,+60] | reaction-sign sort | **Date-format bug + no estimates** | Moderate (fix data) |
| Board meeting | announce date | [−5,+5] | mkt-model | Outcome unknown pre-event | Weak |
| Index inclusion | **PIT needed** | [−20,+20] | mkt-model | **No historical membership** | Blocked |
| F&O ban | **collect fwd** | [−5,+10] | mkt-model | fo_ban empty now | Future |
| IPO listing | listing date | [0,+20] | n/a (no benchmark) | Survivorship + GMP selection | Future |

**Highest-value event studies for you:** insider cluster-buy and bulk-deal accumulation — both ready, both have product/dashboard value, both modest-but-real edge as overlays (not standalone).

---

# SECTION 8 — DERIVATIVES RESEARCH BLUEPRINT

All from `fo_data` (+ options_pcr_daily, options_max_pain, gamma_exposure_daily, participant_oi). **Reminder:** greeks/GEX are index-only & computed.

| Analytic | Data | Calculation | Interpretation | False interpretation | Backtestable? | Dashboard widget |
|---|---|---|---|---|---|---|
| Futures buildup | fo_data front fut | price Δ × OI Δ quadrant | LB/SB/SC/LU | "OI up = bullish" (ignores price) | Yes | Buildup heatmap |
| Rollover | fo_data near/far | far-OI/(near+far) at expiry | conviction into next series | High rollover ≠ direction | Yes | Rollover % gauge |
| Cost-of-carry | fo_data,stock_data | (fut−spot)/spot×(365/dte) | funding/sentiment | Ignores dividends | Partial | Carry line |
| Basis | fo_data,stock_data | fut−spot | rich/cheap | Stale spot at EOD | Partial | Basis monitor |
| OI concentration | fo_data options | OI by strike; top walls | S/R magnets | Walls shift intraday | Yes | OI profile bars |
| Option positioning | fo_data CE/PE | CE-OI vs PE-OI by strike | skew/positioning | EOD ≠ intraday flow | Yes | Chain map |
| PCR regime | options_pcr_daily | PCR percentile | extreme sentiment | Trends ignore PCR | Yes | PCR band |
| Max-pain distance | options_max_pain | spot−maxpain | expiry pin pull | Weak in trends | Yes | Distance dial |
| IV/RV spread | option_greeks,indices | IV−realized | vol risk premium | Computed IV bias | Yes (index) | VRP chart |
| GEX regime | gamma_exposure_daily | dealer Γ sign/level | vol regime | Model-dependent | Index only | GEX regime light |
| Dealer positioning | gamma_exposure_daily | Γ flip levels | instability zones | Computed assumption | Index only | Flip-level marker |
| Expiry-week behavior | fo_data,indices | day-of-week ret profile | pin/volatility | Overfit to few expiries | Yes | Expiry seasonality |
| Participant positioning | participant_oi | FII/Client net-long | smart vs dumb money | Aggregate ≠ stock-level | Yes | Participant gauge |
| Short-cover/long-unwind | fo_data | price↑OI↓ / price↓OI↓ | reversal detection | Noise on low-OI names | Yes | Reversal flags |
| F&O stock risk dashboard | fo_data | OI%MWPL proxy, basis, buildup | per-name risk | proxy ≠ official MWPL | Partial | Stock F&O card |

**Strongest derivatives product:** a **stock-level F&O positioning dashboard** (buildup quadrant + rollover + basis + OI walls) across the ~190 F&O names — this is monetizable and the data fully supports it. **Weakest:** anything leaning on GEX as truth (index-only, computed).

---

# SECTION 9 — MACRO & CROSS-ASSET RESEARCH

**Frequency alignment:** resample everything to a common business-day index; **forward-fill macro with its publication lag** (CPI ~2wk, GDP ~2mo) — never align to reference-period date (that's lookahead). Features standardized as 1y/3y z-scores.

| Model | Data | Lag assumption | Features | Method | Output | Risk | Value |
|---|---|---|---|---|---|---|---|
| Market regime classifier | global_indices,indices,macro | release lags | trend, vol, breadth, yields z | rule-based state machine → later HMM | bull/bear/neutral | overfit states | High (gate) |
| Risk-on/off | global_indices | next-day | risk vs safe-haven ratio, VIX | composite z | RO/RO score | regime-dependent | Med |
| Rate-sensitive sectors | macro,indices | lagged | UST/India yield Δ | rolling regression β | sensitivity map | unstable β | Med |
| USD/INR impact | global_indices,stock_data | same-day | INR β baskets | regression | importer/exporter baskets | β drift | Med |
| Crude-sensitive | global_indices,indices | same-day | Brent β | regression | OMC/aviation baskets | event-driven | Med |
| US-yield → India equity | macro,indices | 1d lag | UST10Y Δ | lead-lag reg | impact estimate | weak/noisy | Low-Med |
| VIX shock | global_indices,indices | next-day | VIX spike z | conditional fwd-ret | playbook | rare events | Med |
| Global lead-lag | global_indices,indices | overnight | SPX/Asia overnight | lagged corr | gap predictor | regime shifts | Med |
| Macro drawdown warning | all macro+breadth | lagged | composite stress z | threshold | warning light | false alarms | Med |
| Macro allocation | all macro | monthly | regime state | tilt rules | exposure dial | slow | Med |

**Honest take:** macro here is a **slow context/gate**, not a signal generator. Best ROI = a single **composite market-regime light** that turns your momentum book's aggressiveness up/down. Don't build 10 macro models; build 1 good regime classifier.

---

# SECTION 10 — MUTUAL FUND ANALYTICS

From `mf_nav_history` (37,977 schemes), `mf_industry_monthly`, `mf_scheme_master`. **NAV ≠ holdings** — repeat to every stakeholder: you can rank and risk-profile funds; you cannot analyze what they own, overlap, or concentration *of holdings*.

| Product | Tables | Metrics | Charts | User value | $ | Missing-data limit |
|---|---|---|---|---|---|---|
| Fund ranking | nav,scheme | 1/3/5y CAGR, rolling percentile | rank table, percentile bands | High | High | survivorship of closed schemes — verify |
| Category rotation | industry | net flow, AUM Δ, category return | flow heatmap | High | High | category remaps |
| AMC performance | nav,scheme | AMC avg percentile | AMC scorecard | Med | Med | — |
| Rolling returns | nav | rolling N-yr return dist | rolling chart | High | Med | dividend-plan NAV resets |
| Risk-adjusted | nav | Sharpe/Sortino/Calmar/Info | radar | High | High | benchmark mapping |
| Drawdown | nav | max DD, recovery time | underwater | High | Med | — |
| SIP returns | nav | XIRR sim | SIP calculator | High | High | — |
| Consistency | nav | % windows top-quartile | consistency bar | High | High | — |
| Flow-vs-perf | industry,nav | flow lead/lag return | scatter | Med | Med | category-level only |
| AUM concentration | industry | AMC/category share | treemap | Med | Med | scheme-AUM missing |
| Category trend | industry | flow/AUM trend | trend lines | Med | Med | 2019+ only |
| Survival/closure risk | nav | NAV-staleness/merger flags | risk tags | Med | Med | needs closure metadata |

**Best MF product to monetize first:** a **risk-adjusted fund scorecard + SIP backtester** (consistency, rolling returns, drawdown, Sharpe) — fully supported, genuinely useful to retail, low compliance risk (factual, not advice). This is arguably your **fastest path to a paid product**.

---

# SECTION 11 — MACHINE LEARNING / AI RESEARCH (brutally realistic)

**What ML can usefully do here:** cross-sectional **ranking** (relative, not absolute), **regime classification**, **volatility forecasting**, **drawdown/event probability**, **anomaly detection**, **fund ranking**. **What it should not do:** predict next-day absolute returns (signal-to-noise ~0; you'll fit noise), price single illiquid names, or replace the adjusted-price/PIT plumbing.

**Why next-day return prediction is weak:** daily equity returns are ~98% noise; any model "works" in-sample by leaking. **Better targets:** (a) **cross-sectional rank** of forward 1–3m return (relative is more learnable), (b) **binary regime** label, (c) **vol bucket**, (d) **P(drawdown>X in 20d)**. Use **rank/IC objectives**, not MSE on returns.

**Leakage prevention (non-negotiable):** purged + embargoed walk-forward CV (time-series split with a gap ≥ holding period); features computed **as-of** with publication lags; **adjusted prices only**; no survivorship (delisted names must be in training); no normalization across the full sample (fit scalers on train fold only).

**Models — start / avoid:** Start with **gradient-boosted trees (LightGBM/XGBoost) on engineered features** + simple logistic for regimes. Avoid (initially) deep nets, LSTMs on raw prices, and anything end-to-end on OHLCV — they overfit and you can't interrogate them. Interpret via SHAP / permutation importance; **monitor decay** with rolling out-of-sample IC and feature-stability tracking.

| Use case | Target | Features | Model | Validation | Leakage risk | Success metric | Value | Diff |
|---|---|---|---|---|---|---|---|---|
| Stock ranking | fwd 1–3m rank | momentum, vol, delivery, liquidity, F&O buildup, breadth-regime | LightGBM ranker | purged WF | scaler/PIT | rank-IC, decile spread | **High** | M |
| Breakout probability | P(20d breakout) | compression, RVOL, trend, regime | GBM classifier | purged WF | label timing | AUC, precision@k | Med | M |
| Drawdown probability | P(−X% in 20d) | vol, regime, breadth, DD depth | GBM | purged WF | regime leak | recall, Brier | Med-High | M |
| Volatility forecasting | realized vol 20d | past vol, IV, regime, range | GBM/HAR | WF | overlap | QLIKE, MAE | Med | M |
| Regime classification | bull/bear/vol state | breadth, trend, macro, GEX | HMM/logistic | WF | label leak | regime stability | High | M |
| Earnings reaction | post-result drift sign | reaction t0, momentum, size | GBM | event-CV | date bug | AUC | Med | H |
| Event impact | CAR sign | event type, liquidity, regime | GBM | event-CV | event leak | AUC | Med | M |
| Sector rotation | next-month sector rank | sector RS, breadth, macro | ranker | WF | alignment | rank-IC | Med | M |
| Liquidity risk | P(turnover collapse) | turnover trend, delivery | GBM | WF | — | recall | Med | L |
| Anomaly detection | outlier flag | price/volume/delivery z | IsolationForest | rolling | — | precision | Med | L |
| MF ranking | fwd fund percentile | rolling return/risk/consistency | ranker | WF | survivorship | rank-IC | Med-High | L |
| IPO risk scoring | listing-return bucket | GMP, subscription, sector | GBM | (collect first) | sparse | AUC | Low | M |

**ML verdict:** treat ML as a **factor-combiner and ranker on top of clean features**, deployed in **Phase 9 — last**. Your edge comes from data cleanliness + sensible features, not model sophistication.

---

# SECTION 12 — BACKTESTING ENGINE ARCHITECTURE

**Data layer**
- Raw: `stock_data`, `fo_data`, `stock_delivery`, etc. (read-only).
- Cleaned: dedup, gap-flag, outlier-winsor → `clean_*` views.
- **Adjusted prices:** materialize `stock_data_adj` from `corporate_actions` (cumulative back-adjust factor for split/bonus/dividend). **First build.**
- Corp-action handling: total-return series; strike-adjust F&O on splits.
- Symbol mapping: ISIN-keyed master to survive symbol changes (use registries).
- **Delisted handling:** keep in universe to last trade date; mark exit; never forward-fill.
- **PIT fundamentals:** join fundamentals only on/after `financial_results.filing_date`.
- Feature store: as-of feature table keyed (symbol, date), built with publication lags.

**Strategy layer:** signal → cross-sectional rank → universe/liquidity filter → portfolio construction (equal/inverse-vol/optimizer) → position sizing (vol-target) → entry/exit → monthly rebalance → risk limits (single-name, sector, beta, turnover caps).

**Execution layer:** slippage = half-spread + impact; transaction cost 0.15–0.25% round-trip (brokerage+STT+exchange+stamp+GST); liquidity filter (order ≤ 5–10% ADV); impact model = k·√(order/ADV); **capacity estimate** per strategy.

**Validation layer:** walk-forward (expanding) · out-of-sample holdout · regime-split tests · block bootstrap · Monte Carlo on trade sequence · **multiple-testing / false-discovery control** (Deflated Sharpe, Bonferroni on # strategies tried) · parameter-sensitivity heatmaps · factor-decay.

**Performance metrics:** CAGR, Sharpe, Sortino, max DD, Calmar, vol, win rate, profit factor, avg win/loss, turnover, exposure, beta, alpha, Information Ratio, **hit-rate by regime**, capacity, **slippage sensitivity curve** (Sharpe vs assumed cost).

**The one rule:** if a strategy's Sharpe collapses when you raise costs from 0.1% to 0.3%, it was never real.

---

# SECTION 13 — DASHBOARD & PRODUCT BLUEPRINT

Format per dashboard: **User · Problem · Tables · Widgets · Alerts · Edge · Diff · $ · Free/Paid · MVP → Advanced**

1. **Market Regime** — *Trader.* Is the market risk-on? `market_breadth,indices_data,global_indices,macro`. Widgets: regime light, %>200DMA, breadth trend, vol gauge. Alerts: regime flip. MVP: breadth+trend light → Adv: macro composite + HMM. Paid. Diff M.
2. **Breadth** — *Trader.* Internal health. `stock_data,market_breadth`. Adv/dec line, NH-NL, %>50/200DMA, sector breadth grid. Alert: thrust/deterioration. Free MVP / Paid sector grid. Diff L.
3. **Sector Rotation** — *PM.* Where's leadership? `indices_data,index_constituents`. RS heatmap, rotation quadrant. Paid. Diff M.
4. **Survivorship-Honest Screener** — *Everyone.* Honest momentum/quality screen incl. delisted history. `stock_data_adj,stock_delivery`. Filters, factor sliders, backtest preview. **Flagship paid.** Diff M.
5. **Signal Dashboard** — *Trader.* Today's signals. all signal tables. Ranked lists, signal cards. Alerts: new signal. Paid. Diff M.
6. **Backtest Dashboard** — *Quant/resume.* Validate ideas. engine outputs. Equity curve, metrics, regime split, cost-sensitivity. Paid/portfolio. Diff H.
7. **F&O Positioning** — *F&O trader.* Buildup/rollover. `fo_data,participant_oi`. Buildup heatmap, rollover, basis, OI walls. Alert: aggressive buildup. **Strong paid.** Diff M.
8. **Options Chain Intelligence** — *Options trader.* Positioning. `fo_data,options_pcr_daily,options_max_pain`. Chain map, PCR band, max-pain dial. Paid. Diff M.
9. **Gamma Exposure** — *Index trader.* Vol regime. `gamma_exposure_daily`. GEX regime light, flip levels. *Caveat banner (index/computed).* Paid niche. Diff H.
10. **Deals (Insider/Bulk/Block/Short)** — *Everyone.* Smart-money tracking. `insider_trading,bulk/block/short_deals`. Feed, net-flow charts, investor tracker, CAR overlay. Alert: cluster buy. **Strong paid.** Diff M.
11. **Corporate Events** — *Investor.* Action calendar. `corporate_actions`. Calendar, ex-date list. Free. Diff L.
12. **Results Calendar** — *Trader.* Earnings risk. `board_meetings,financial_results`. Calendar + reaction history. Free/Paid. Diff L (after date fix).
13. **Macro Risk** — *PM.* Cross-asset stress. macro+global. Stress gauges, yield/USD/crude panels. Paid. Diff M.
14. **Mutual Funds** — *Retail investor.* Pick funds. `mf_nav_history,mf_industry,mf_scheme`. Scorecard, SIP backtester, rolling returns, drawdown, category rotation. **Fastest paid product.** Diff L-M.
15. **IPO Tracker** — *Retail.* IPO intel. `ipo_data`. GMP, subscription, listing. Free (collect history). Diff L.
16. **Portfolio Risk** — *Investor.* My-portfolio risk. user holdings + stock_data + corr. Exposure, beta, sector, DD. Paid. Diff M.
17. **Alert Center** — *Everyone.* Cross-dashboard alerts. all. Rule builder, delivery (TG/email). **Retention driver.** Diff L-M.
18. **Research Notebook** — *Quant/resume.* Reproducible studies. all. Saved queries, event studies, charts. Portfolio showcase. Diff M.

**Build order (product):** #14 MF scorecard (fast, low-risk) → #4 honest screener → #10 deals → #7 F&O positioning → #1 regime. These five are the monetizable core.

---

# SECTION 14 — MONETIZATION STRATEGY

| Channel | Customer | Pays for | MVP | Differentiation | Pricing | Diff | Compliance risk | Data-license risk | Trust need |
|---|---|---|---|---|---|---|---|---|---|
| Retail dashboards | Active retail | Regime/breadth/F&O views | Regime+breadth web app | Survivorship-honest + delivery data | ₹299–999/mo | M | Low (factual) | Med (NSE T&C) | Med |
| Premium screener | Swing traders | Honest factor screen + backtest preview | Screener with 5 factors | Delisted-inclusive, cost-aware | ₹499–1499/mo | M | Low-Med | Med | Med |
| TG/WhatsApp alerts | Retail | Timely signal/deal alerts | Cluster-buy + buildup alerts | Curated, low-noise | ₹199–599/mo | L | **Med-High (advice line)** | Med | High |
| Research reports | Serious retail/advisors | Weekly regime+positioning+deals report | PDF/newsletter | Data-backed, no tips | ₹999–2999/mo | L | Low (research, not advice) | Med | High |
| API access | Devs/quants | Clean adjusted prices, F&O, deals feeds | REST over curated tables | Survivorship-free history | ₹5k–50k/mo | M | Low | **High (redistribution)** | Med |
| Advisor analytics | RIAs/PMS | Custom factor/MF analytics | White-label scorecards | Bespoke | project-based | M | Med | Med | High |
| MF analytics product | Retail/distributors | Fund scorecards + SIP tools | MF dashboard | Consistency/risk-adjusted depth | ₹199–699/mo | L | Low | Low | Med |
| F&O dashboard | Options/F&O traders | Positioning intelligence | Buildup+chain app | Stock-level buildup | ₹699–1999/mo | M | Med | Med | High |
| Regime dashboard | All | Macro/breadth regime | Regime light app | Composite + history | ₹299–799/mo | M | Low | Med | Med |
| Educational | Aspiring quants | Course on this stack | "Build a quant warehouse" course | Real 130M-row dataset | ₹2k–10k once | L | Low | Low | Med |
| Resume/showcase | You | Career capital | Public dashboard + writeups | Institutional depth | n/a | L | n/a | n/a | n/a |
| B2B data intelligence | Fintechs/media | Curated derived datasets | Licensed feeds | Derived analytics | contract | H | Med | **High** | High |

**Critical compliance note (India):** anything resembling **buy/sell tips = SEBI RA/IA territory.** Stay on the **factual/analytics/educational** side (show data and let users decide), or register. **Highest-margin lowest-risk start:** MF scorecard + research newsletter + honest screener. **Data-license caveat:** NSE/AMFI redistribution terms restrict reselling raw data — sell *derived analytics and views*, not raw dumps.

---

# SECTION 15 — DATA GAPS & UPGRADE PLAN

| Rank | Missing data | Why it matters | Unlocks | Priority | Source difficulty | Essential? |
|---|---|---|---|---|---|---|
| 1 | **Materialized adjusted prices** | Everything price-based is wrong without it | All backtests, momentum, events | **P0** | Low (build from `corporate_actions`) | **Essential** |
| 2 | **Historical index membership (PIT)** | Survivorship in index studies/universe | Sector-neutral factors, inclusion studies, honest universe | **P0** | Med | **Essential** |
| 3 | **Point-in-time fundamentals + filing dates** | Non-PIT = lookahead | Value/quality/growth factors, PEAD | **P1** | High | Essential (for investing) |
| 4 | **F&O expiry calendar (clean)** | Rollover/expiry analytics correctness | Rollover, expiry studies | **P1** | Low (derive from `fo_data`) | Essential (F&O) |
| 5 | **Corporate-action→price linkage validation** | Trust in adjustment | Clean total-return | **P1** | Low | Essential |
| 6 | **Promoter pledge data** | Major risk signal | Risk overlays, distress | **P2** | Med | Optional-high |
| 7 | **MF holdings (portfolio)** | NAV≠holdings | Overlap, concentration, true fund analytics | **P2** | Med-High | Optional-high |
| 8 | **Analyst estimates** | Real earnings surprise | Proper PEAD/quality | **P2** | High (paid) | Optional |
| 9 | **Sector/industry for ALL names** | Only 507 now | Sector-neutral everything | **P2** | Med | Essential (factors) |
| 10 | **Full announcement text** | Metadata only | NLP/event tagging | **P3** | Med | Optional |
| 11 | **Institutional/FII holdings (stock-level)** | Ownership factor | Ownership research | **P3** | High | Optional |
| 12 | **Intraday data** | EOD-only | Microstructure, execution | **P3** | High (storage) | Optional (not your horizon) |
| 13 | **Borrow/lending (SLB) data** | Short constraints | Squeeze/short signals | **P3** | Med | Optional |
| 14 | **Results actuals vs expectations** | Surprise quality | PEAD | **P3** | High | Optional |
| 15 | **Credit ratings** | Distress/quality | Risk overlay | **P3** | Med | Optional |
| 16 | **FII/DII deep history** | Current 30 rows useless | Flow analytics | **P2** | Med | Essential (flows) |
| 17 | **Promoter shareholding for more names** | 174 too thin | Ownership factor | **P3** | Med | Optional |
| 18 | **Economic calendar** | Event-risk timing | Macro overlays | **P4** | Low | Optional |
| 19 | **Social sentiment** | — | Sentiment signals | **P4** | High | Optional |
| 20 | **Order-book data** | — | Microstructure | **P4** | Very High | No (not your horizon) |

**Do P0 (adjusted prices + PIT membership) before any serious research.** They're cheap (you already have the raw inputs) and they gate trustworthiness.

---

# SECTION 16 — EXECUTION ROADMAP

| Phase | Goals | Key tasks | Deliverables | Skills | Diff | Time | Depends | Avoid | Success criteria |
|---|---|---|---|---|---|---|---|---|---|
| **0 Audit** | Know what's true | Validate 10 core tables; recompute breadth/derived from raw; find lookahead | Data-quality report | SQL | L | 1wk | — | trusting inventory | Every core table has a validation test passing |
| **1 Clean/normalize** | Trustworthy base | Build `stock_data_adj`; PIT universe; ISIN master; fix result-date bug | Clean layer + adj prices | SQL/Python | M | 2wk | P0 | skipping adjustment | adj series matches index TR within tolerance |
| **2 Feature engineering** | As-of feature store | Momentum/vol/delivery/liquidity/F&O/breadth features w/ lags | Feature table | Python | M | 2wk | P1 | normalizing across full sample | features reproducible as-of |
| **3 Analytics/dashboards** | First products | Regime, breadth, screener, MF scorecard | 3–4 dashboards | Python/viz | M | 3–4wk | P2 | over-engineering | live dashboards users can use |
| **4 Signal research** | Find ready edges | Build the 5 ready factors + delivery/insider/deal overlays | Signal library + IC report | Quant | M | 4wk | P2 | data mining w/o cost | rank-IC stable OOS |
| **5 Backtest engine** | Honest validation | Walk-forward, costs, capacity, FDR control | Backtester | Quant/eng | H | 4wk | P4 | optimistic costs | Sharpe survives cost stress |
| **6 Factor research** | Composite factor | Combine 5 ready factors; neutralize; decay test | Factor portfolio | Quant | H | 4wk | P5 | fundamental factors now | positive net-of-cost L/S |
| **7 Derivatives analytics** | F&O product | Buildup/rollover/basis/chain dashboards | F&O dashboard | Derivatives | M | 3wk | P2 | GEX over-reliance | per-name positioning live |
| **8 Macro regime** | Context gate | 1 composite regime classifier | Regime model | Macro | M | 2wk | P2 | 10 macro models | improves momentum Sharpe as gate |
| **9 ML models** | Combiner/ranker | LightGBM ranker on feature store; purged CV | ML ranking layer | ML | H | 4wk | P6 | deep nets, return-MSE | OOS rank-IC > linear baseline |
| **10 Productization** | Sellable suite | Auth, billing, alerts, polish | Product | Full-stack | H | 6wk+ | P3–7 | scope creep | paying users |
| **11 Monetization** | Revenue | Pricing, compliance, marketing | Revenue | Business | M | ongoing | P10 | SEBI-advice line | first paying cohort |

---

# SECTION 17 — BRUTAL REALITY CHECK

- **Genuinely valuable:** survivorship-free 21yr equity universe; 21yr delivery%; F&O bhavcopy depth; MF NAV history. These four are real assets most retail tools lack.
- **"Big but not necessarily useful":** mf_nav_history's 36.9M rows (NAV-only ceiling); fo_data's 68.9M rows (powerful but you'll use a fraction); macro to 1919 (context, not signal); derived `window_*` tables (until audited).
- **Strongest tables:** `stock_data`, `stock_delivery`, `fo_data`, `mf_nav_history`, `bulk_deals`, `insider_trading`.
- **Weakest tables:** `fii_dii_data` (empty), `fo_ban` (empty), `stock_fundamentals` (empty), `news_headlines`/`google_trends`/`ipo_data` (tiny/recent), `shareholding_history` (174), `index_constituents` (snapshot), `board_meetings` (19).
- **Analyses likely to fool you:** PCR extremes, max-pain pinning, GEX (computed/index), seasonality (`symbol_seasonality`), any fundamental factor (non-PIT), index-inclusion studies (no PIT membership), pairs (multiple-testing).
- **Fake-edge generators:** unadjusted-price momentum (splits create fake gaps), survivorship in any universe sort, fundamentals without filing dates, backtests at 0.05% cost, parameter-optimized breakouts.
- **Good for dashboards, bad for trading:** PCR, max-pain, GEX, participant-OI, news, google trends — great visuals, weak standalone alpha.
- **Good for resume/project value:** the survivorship-free backtest engine, the adjusted-price + corporate-action layer, the event-study framework, the multi-factor IC study, the regime classifier. These *demonstrate institutional thinking* — that's what impresses.
- **Can become real paid products:** MF scorecard, honest screener, deals tracker, F&O positioning dashboard, regime/breadth app.
- **Build first:** adjusted prices + PIT universe → momentum+delivery+breadth backtest → MF scorecard product.
- **Stop obsessing over:** greeks/GEX (index-only/computed), squeezing fundamental factors out of non-PIT data, ML before the data layer is clean, scraping ever-more datasets (you have enough — *use* it).
- **What an institution would criticize:** no PIT fundamentals, no historical index membership, unadjusted prices, computed (not vendor) IV/greeks, single-source/no cross-validation, no documented data lineage, empty flagship-sounding tables.
- **What would make this seriously impressive:** a fully **survivorship-free, corporate-action-adjusted, cost-and-capacity-aware walk-forward backtest** of a multi-factor momentum book, with rank-IC decay, regime-split performance, and a deflated-Sharpe significance test — published as a clean writeup. *That* is portfolio-defining.

---

# SECTION 18 — FINAL RANKED PRIORITIES

Format: **Rank · Idea · Tables · Why · Readiness · Diff · Edge · $ · Priority/10**

### A. Top 25 — Trading research
1. Adjusted-price + CA layer · stock_data,corporate_actions · gates all · H · M · enabler · M · 10
2. PIT liquid universe · bhavcopy,fo_data · kills survivorship · H · M · enabler · M · 10
3. 12-1 momentum book · stock_data_adj · core edge · H · M · H · M · 10
4. Delivery-confirmed momentum · +stock_delivery · differentiated · H · M · H · H · 10
5. Breadth regime gate · market_breadth · timing filter · H · L · M · H · 9
6. Multi-factor composite (mom+lowvol+illiq+delivery) · +derived · robust · H · M · H · H · 9
7. Walk-forward backtest harness · all clean · honesty · H · H · enabler · M · 9
8. Capacity/slippage estimator · stock_data,delivery · realism · H · M · H · M · 9
9. Futures long/short buildup · fo_data · positioning · H · M · M · H · 8
10. Rollover analytics · fo_data · expiry edge · H · M · M · H · 8
11. Insider cluster-buy overlay · insider_trading · event drift · H · M · M · H · 8
12. Bulk-deal accumulation · bulk_deals · smart money · H · M · M · H · 8
13. Residual momentum · stock_data,indices · cleaner · H · M · H · M · 8
14. Low-vol factor · stock_data · anomaly · H · M · M · M · 8
15. Delivery-spike accumulation · stock_delivery · under-arbitraged · H · M · H · H · 8
16. Momentum crash protection · +breadth · drawdown control · H · M · M · M · 8
17. Multi-timeframe momentum blend · stock_data · robustness · H · M · H · M · 8
18. Sector RS rotation · indices_data · leadership · M · M · M · H · 7
19. Factor decay/IC monitor · derived · trust · H · M · H · M · 8
20. Participant-OI sentiment · participant_oi · overlay · H · L · L-M · H · 6
21. Liquidity-squeeze warning · delivery · risk · H · M · M · M · 6
22. PCR extreme (overlay only) · options_pcr_daily · contrarian · H · L · L-M · H · 6
23. VIX-shock playbook · global_indices · regime · H · M · M · M · 6
24. Short-deal squeeze setup · short_deals,fo_data · niche · H · M · M · M · 6
25. Strategy-decay live monitor · live · longevity · H · M · enabler · M · 7

### B. Top 25 — Investing research
1. PIT fundamentals build (filing dates) · financial_results,quarterly_* · unlocks value/quality · L · H · enabler · M · 9
2. Sector classification (all names) · source new · neutralization · L · M · enabler · M · 9
3. Low-vol long-only portfolio · stock_data · defensive · H · M · M · M · 8
4. Liquidity-premium decile · stock_data,delivery · risk premium · H · M · M · M · 7
5. Quality factor (once PIT) · annual/quarterly · core · L · H · M · M · 7
6. Value factor (once PIT) · index_valuation,quarterly · core · L · H · M · M · 7
7. Long-only momentum tilt (cost-aware) · stock_data_adj · investable · H · M · H · M · 8
8. Index valuation-regime allocation · index_valuation · timing tilt · H · M · M · H · 7
9. MF risk-adjusted scorecard · mf_nav · product · H · L · M · H · 8
10. MF consistency score · mf_nav · selection · H · M · M · H · 7
11. SIP backtester · mf_nav · tool · H · M · L · H · 7
12. Dividend/total-return series · stock_data,CA · correctness · H · M · enabler · L · 7
13. Promoter-conviction (expand) · shareholding · ownership · M · M · L-M · L · 5
14. Quality+momentum combo · stock_data,fundamentals · QMJ-style · L · H · M · M · 6
15. Sector risk-parity allocation · indices_data · diversification · H · M · M · M · 6
16. Drawdown/recovery profiles · stock_data · risk · H · L · M · M · 6
17. Low-vol + dividend screen · stock_data,CA · income tilt · M · M · M · M · 6
18. Macro regime allocation dial · macro · context · M · M · M · M · 6
19. Earnings-quality (accruals) · quarterly_* · once PIT · L · H · M · M · 5
20. Insider-buy long-term holding · insider_trading · conviction · H · M · M · M · 6
21. Survivorship-honest long-run study · stock_data_adj · credibility · H · M · enabler · M · 8
22. Cross-asset diversification map · global_indices · allocation · H · M · L-M · M · 5
23. Fund flow-vs-performance · mf_industry,nav · behavioral · M · M · M · M · 5
24. Category rotation tilt · mf_industry · allocation · H · L · L-M · H · 6
25. Volatility-targeted equity sleeve · stock_data · risk control · H · M · M · M · 6

### C. Top 25 — Dashboard/product
1. MF scorecard + SIP tool · mf_* · H · L · — · **H** · 9
2. Survivorship-honest screener · stock_data_adj,delivery · H · M · — · H · 9
3. Deals tracker (insider/bulk/block) · deals,insider · H · M · — · H · 9
4. F&O positioning dashboard · fo_data,participant_oi · H · M · — · H · 8
5. Market-regime app · breadth,macro,global · H · M · — · H · 8
6. Breadth dashboard · stock_data,breadth · H · L · — · M · 8
7. Sector-rotation map · indices,constituents · M · M · — · H · 7
8. Options chain intelligence · fo_data,pcr,maxpain · H · M · — · H · 7
9. Alert center · all · H · M · — · H · 8
10. Corporate-events calendar · corporate_actions · H · L · — · M · 7
11. Results calendar · board_meetings,financial_results · M · L · — · M · 6
12. Macro-risk dashboard · macro,global · H · M · — · M · 6
13. Portfolio-risk analyzer · stock_data,corr · M · M · — · H · 7
14. Category-flow (MF) dashboard · mf_industry · H · L · — · H · 7
15. Signal dashboard · signal tables · M · M · — · H · 7
16. Backtest dashboard · engine · M · H · — · M · 7
17. IPO tracker · ipo_data · M · L · — · M · 5
18. GEX/vol-regime (index, caveated) · gamma_exposure · M · H · — · M · 5
19. Insider-investor tracker · insider_trading · H · M · — · H · 6
20. Liquidity/capacity explorer · stock_data,delivery · H · M · — · M · 6
21. Index-valuation regime panel · index_valuation · H · L · — · M · 6
22. Correlation-network map · stock_data · M · H · — · M · 5
23. Research notebook (public) · all · M · M · — · — · 7
24. Rollover/expiry monitor · fo_data · H · M · — · H · 6
25. Drawdown monitor · stock_data,indices · H · L · — · M · 6

### D. Top 25 — ML/AI
1. Cross-sectional rank ranker (LightGBM) · feature store · H · M · H · M · 9
2. Feature store (as-of, lagged) · clean tables · H · M · enabler · M · 9
3. Purged walk-forward CV harness · features · H · M · enabler · M · 9
4. Regime classifier (HMM/logistic) · breadth,macro · H · M · H · M · 8
5. Volatility forecaster · indices,greeks · H · M · M · M · 7
6. Drawdown-probability model · breadth,vol · H · M · M · M · 7
7. Breakout-probability model · price,vol · H · M · M · M · 6
8. Factor-combiner (ML over 5 factors) · features · H · M · H · M · 8
9. Anomaly detection (data QA + setups) · price/delivery · H · L · M · L · 6
10. MF-ranking ranker · mf_nav · H · L · M · H · 7
11. Earnings-reaction classifier · financial_results · L · H · M · M · 5
12. Sector-rotation ranker · indices · M · M · M · M · 6
13. Liquidity-risk classifier · delivery · H · L · M · M · 6
14. SHAP feature-importance pipeline · models · H · L · enabler · L · 7
15. Model-decay monitor · OOS IC · H · M · enabler · M · 7
16. Event-impact (deal) classifier · deals · H · M · M · M · 6
17. Vol-of-vol / tail model · greeks,indices · M · H · L-M · M · 4
18. Crowding detector · factor exposures · M · H · M · M · 5
19. Correlation-regime detector · stock_data · M · M · M · M · 5
20. IPO-risk scorer (collect first) · ipo_data · L · M · L · M · 4
21. NLP event-tagger (forward news) · news · L · H · L · M · 3
22. Macro-nowcast (slow) · macro · L · H · L · M · 4
23. Pairs-selection ML · stock_data · M · H · M · M · 5
24. Position-sizing RL (advanced, later) · all · L · VH · M · L · 3
25. Ensemble meta-ranker · all models · M · H · M · M · 5

---

# SECTION 19 — IMMEDIATE NEXT STEPS

### First 10 things this week
1. Build & materialize **`stock_data_adj`** (split/bonus/dividend back-adjustment) from `corporate_actions`; spot-check against 10 known split events.
2. Build the **PIT liquid universe** table (monthly, from raw bhavcopy turnover) — survivorship-free membership.
3. **Audit the derived `window_*`/`symbol_*` tables** for baked-in lookahead (re-derive one symbol from raw, diff).
4. **Fix `financial_results` date parsing** (`01-Feb-202` is truncated/dirty) and attach filing dates.
5. Recompute **`market_breadth`** from raw and confirm it's as-of (not forward-filled).
6. Validate **`fo_data` expiry calendar** (distinct expiries per series; continuity).
7. Reconcile **`stock_delivery` qty vs `stock_data.volume`** for outliers/definition breaks (pre/post 2011).
8. Write a **data-quality report** (one row per core table: coverage, gaps, tests passed).
9. Stand up the **cost+capacity model** constants (STT/brokerage/impact) as a shared module.
10. Draft the **MF scorecard MVP** spec (fastest monetizable product).

### First 10 tables to validate
1. `stock_data` (adjustment correctness) 2. `corporate_actions` (ratio parsing) 3. `stock_delivery` (definition breaks) 4. `fo_data` (expiry/OI continuity) 5. `market_breadth` (as-of) 6. `insider_trading` (txn classification, dual dates) 7. `bulk_deals` (dedup) 8. `index_constituents` (confirm snapshot-only) 9. `financial_results` (date bug) 10. `mf_nav_history` (plan dedup, closed-scheme survivorship).

### First 10 signals to build
1. 12-1 momentum (adj) 2. Delivery-confirmed momentum 3. Breadth regime gate 4. Low-vol factor 5. Amihud liquidity factor 6. Futures long/short buildup 7. Insider cluster-buy overlay 8. Bulk-deal accumulation 9. Delivery-spike accumulation 10. Multi-factor composite (1+4+5+delivery).

### First 5 dashboards to build
1. MF scorecard + SIP backtester 2. Survivorship-honest screener 3. Deals tracker 4. Market-regime app 5. F&O positioning dashboard.

### First 5 research papers/projects to write
1. "Survivorship-free momentum in Indian equities: a cost- and capacity-aware walk-forward study."
2. "Does delivery% add information to price momentum? A 21-year study."
3. "Breadth regimes as a momentum timing filter on the NSE."
4. "Insider cluster-buying and bulk-deal accumulation: event-study drift (2006–2026)."
5. "F&O futures positioning (price×OI) as a swing-horizon signal across NSE F&O stocks."

### Biggest 10 mistakes to avoid
1. Backtesting on **unadjusted** prices (fake split gaps = fake momentum).
2. Using the **snapshot** index membership historically (survivorship).
3. Treating **non-PIT fundamentals** as known at the time (lookahead).
4. Assuming **0.05% costs** — mid/small-cap impact is brutal; stress-test costs.
5. Trusting **derived `window_*` tables** before auditing their as-of construction.
6. Reading edge into **PCR/max-pain/GEX** (dashboards, not standalone alpha; GEX is index-only/computed).
7. **Multiple-testing** your way to a "great" strategy (use deflated Sharpe / FDR control).
8. Building **ML before the clean data layer** (you'll model leakage).
9. Trading **illiquid names** the backtest "loves" but you can't fill.
10. Crossing into **SEBI advice territory** for monetization (stay factual/analytics/educational, or register).

---

*End of blueprint. The throughline: your data's true strength is a survivorship-free, 21-year, daily Indian equity + delivery + F&O dataset — ideal for 1–6m momentum/breadth/F&O research and for dashboard products. Fix the adjusted-price and PIT-membership plumbing first; everything trustworthy is downstream of those two.*
