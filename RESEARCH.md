# Cross-Sectional Momentum, Delivery, and Low-Volatility in Indian Equities
### A survivorship-free, cost- and regime-aware study (2005–2026)

*MICC research note. Methodology + reproducible results. Not investment advice.*

---

## Abstract

Using a 21-year, survivorship-free daily panel of Indian equities (NSE), we build a
point-in-time feature store and test a composite cross-sectional signal combining
**12-1 price momentum**, **52-week-high proximity**, **delivery-volume strength**, and
**low volatility**. On the liquid top-500 (by trailing turnover, equity-only) universe,
a monthly long-only top-decile book with a regime gate delivers, net of 30 bps/side costs,
a Sharpe of **1.12** (3-factor breadth-gated). Replacing the single breadth gate with a 4-signal
macro **regime classifier**, and weighting positions by inverse volatility, raises this to a
**walk-forward out-of-sample Sharpe of 1.53** (CAGR 23.9%, Calmar 1.26) — versus **0.48** for an
equal-weight benchmark and 1.34 for the breadth-only gate on the same window. The result is stable across three independent sub-periods, survives
walk-forward out-of-sample testing, is robust to parameterization, and remains significant after
deflating for multiple testing (Deflated Sharpe ≈ 100%, N=21 trials). A LightGBM learning-to-rank
model, rigorously walk-forward-validated, **fails to beat the transparent linear composite**
(OOS Sharpe 0.76 vs 1.25) — monthly cross-sectional returns are too noisy for the tree to
generalize. We document honest limitations (capacity ≈ ₹100–250cr, residual survivorship,
snapshot sector data) and find F&O positioning adds no strong cross-sectional edge.

---

## 1. Data and universe

| Component | Detail |
|---|---|
| Source | NSE daily bhavcopy + delivery, 2005-01 → 2026-06 (`stock_data`, `stock_delivery`) |
| Coverage | 4,200 symbols incl. delisted (**survivorship-free**) |
| Adjustment | Split/bonus back-adjusted (`stock_data_adj`) with a per-event **cliff-verification guard** that skips names already adjusted at source |
| Universe | Monthly point-in-time top-500 by trailing-63-day median turnover (`pit_universe`), **ETFs/funds excluded** (ISIN INF vs INE) |
| Identity | ISIN master tracks 276 ticker renames so series stay continuous (`isin_master`) |

**Anti-lookahead discipline.** Every feature is trailing-window only; signals are taken
as-of each month-end close; realized returns are month-end→month-end on adjusted prices;
universe membership and the regime gate are as-of the rebalance. Verified by 29/29
independent pin-to-pin checks including manual recomputation (`verify_phases.py`).

---

## 2. Signals and predictive power (rank-IC)

Mean cross-sectional Spearman rank-IC vs forward return, top-500 universe, 257 months:

| Signal | IC vs 1m | %+ months | IC vs 3m |
|---|---|---|---|
| 52-week-high proximity | +0.051 | 61% | **+0.090** |
| Low volatility (−vol_3m) | **+0.058** | 63% | — |
| Delivery % (1m mean) | +0.045 | 63% | +0.065 |
| 12-1 momentum | +0.041 | 65% | +0.052 |
| Trend (dist. 200DMA) | +0.037 | 62% | +0.065 |
| Realized vol (3m) | −0.051 | 40% | −0.072 |
| Illiquidity (Amihud) | −0.023 | 39% | −0.022 |

Every sign matches theory; magnitudes (~0.04–0.06) are in the legitimate institutional
range, not lookahead-inflated. The **delivery** signal — rarely used in retail tooling —
carries independent predictive power, and **low volatility** is the strongest single factor.

---

## 3. The composite and the decile relationship

The composite is the equal-weight mean of cross-sectional percentile ranks of the component
signals (no fitting). Mean realized monthly return by composite decile (gross, top-500):

```
D1  +0.35%  D2 +0.67%  D3 +0.95%  D4 +0.91%  D5 +1.20%
D6  +1.09%  D7 +1.60%  D8 +1.34%  D9 +1.70%  D10 +1.88%
                                    spread D10−D1 = +1.65%/month
```

The relationship is **monotone across the whole distribution** — the signal sorts returns
everywhere, not just at the tails (the signature of real signal, not a tail artifact).

---

## 4. Strategy results (net of 30 bps/side, 2005–2026)

Monthly rebalance, equal-weight, top-decile, with a breadth regime gate
(invest only when % of stocks above 200-DMA ≥ 50, else cash):

| Strategy | CAGR | Vol | Sharpe | Sortino | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| **A: 3-factor + regime gate** | 15.7% | 13.9% | 1.12 | 1.13 | −17.8% | 0.88 |
| **B: 4-factor (+low-vol) + gate** | 13.6% | 11.2% | **1.19** | **1.26** | **−14.9%** | **0.91** |
| LongOnly D10 (no gate) | 19.6% | 21.9% | 0.94 | 1.05 | −65.9% | 0.30 |
| Benchmark (EW top-500) | 10.1% | 29.3% | 0.48 | 0.67 | −72.5% | 0.14 |
| Long-short (D10−D1) | 9.4% | 30.8% | 0.48 | 0.50 | −79.8% | 0.12 |

**Two findings drive everything:**
1. **The breadth regime gate** transforms risk: it cuts max drawdown from −65.9% (ungated)
   to −17.8% while keeping ~16% CAGR, by sitting in cash during broad downtrends (where
   momentum crashes).
2. **The long-short book is poor** (−80% drawdown): the short leg is destroyed in sharp
   rebounds (momentum crashes). The edge is entirely long-only.

Adding **low volatility** (B) trades ~2% CAGR for a markedly better risk profile
(Sharpe 1.12→1.19, MaxDD −17.8%→−14.9%) — the classic low-vol effect.

---

## 5. Robustness (why this isn't curve-fit)

| Test | Result |
|---|---|
| **Sub-period stability** | Gated Sharpe 0.90 (2005–11) / 1.17 (2012–18) / 1.30 (2019–26) — works every era, rising (no decay) |
| **Walk-forward OOS (2008–26)** | IC-weighted composite (past-data-only weights) Sharpe 1.17; naive equal-weight 1.29 — edge does **not** depend on weight-fitting |
| **Parameter sensitivity** | Sharpe plateau across top-10/20/30% × gate-threshold 40/50/60% (no knife-edge) |
| **Block-bootstrap** | Sharpe 90% CI **[0.73, 1.59]**, P(Sharpe>0)=100% |
| **Probabilistic Sharpe** | PSR(0) ≈ 100% |
| **Deflated Sharpe** | ≈ 100% after deflating for N=21 trials (luck-threshold SR0=0.15) — not a data-mining fluke |

---

## 6. What did NOT work (honest negatives)

- **Sector-neutralization**: with only snapshot sector data (≈49% of historical rows
  classified), demeaning within sector *lowered* Sharpe (1.19→1.02). Not supported by the data.
- **F&O positioning** (PCR, futures-OI change/level): weak cross-sectional IC (|IC| mostly
  <0.02; crowding −0.056 but size-confounded), only 8% universe coverage. A confirmation
  overlay on the ~190 F&O names, not a core factor.
- **Long-short / market-neutral**: dominated by momentum-crash drawdowns; not viable here.

---

## 6b. Advanced extensions (ML, position sizing, regime engine)

| Extension | Result | Verdict |
|---|---|---|
| **LightGBM ranker** (19 features, purged WF CV) | OOS Sharpe 0.76 vs linear 1.25; OOS IC +0.016 vs +0.082 | ML **loses** — overfits the noise; linear wins |
| **Inverse-vol weighting** | Sharpe 1.12, MaxDD −16.4% | marginal; cuts drawdown |
| **+ 12%-vol-target overlay** | Sharpe **1.18**, Sortino **1.60**, Calmar **1.17**, MaxDD −14.0% | real risk-adjusted gain |
| **Capacity (sqrt-impact)** | Sharpe ~1.0 to ₹100cr, ~0.7 at ₹250cr | capacity ≈ **₹100–250cr** |
| **Macro regime gate** (in-sample ≥2/4) | Sharpe 1.43, Sortino 2.00, CAGR 21.9% | beats breadth-only — but threshold chosen in-sample |
| **Macro regime gate** (walk-forward) | **OOS Sharpe 1.56**, Calmar 1.37, MaxDD −19.6% vs breadth-only OOS 1.34 | **validated** — regime beats breadth-only out-of-sample |
| **Combined best** (inverse-vol + WF-regime) | **OOS Sharpe 1.53**, Sortino 2.30, Calmar 1.26, CAGR 23.9% (`bt_best`) | the production config |

The macro regime classifier (breadth + Nifty 200-DMA + S&P 200-DMA + India-VIX-below-median) is the
single most valuable extension; the original breadth-only gate was too conservative (in cash 54% of
months). **Walk-forward validation** (threshold chosen from past data only) confirms the regime gate
robustly beats breadth-only out-of-sample (Sharpe ~1.55 vs 1.34), though the specific ≥2/4 threshold
does *not* survive — the adaptive choice favours ≥1 (more time in market) in 72% of months. Two further
honest findings: (i) the **vol-target overlay does NOT stack** on the regime gate (Sharpe 1.53→1.40) —
the gate already controls risk; (ii) the **ML ranker loses** — validating the research-first design.
Best production config = inverse-vol-weighted top-decile + walk-forward regime gate.

## 7. Limitations

- **Residual survivorship**: ~1,258 name-months dropped for missing next-month price
  (mostly mid-month delistings); dropping delisting losses slightly flatters returns.
- **Capacity**: ~38%/month one-way turnover; real impact in the smaller top-500 names
  exceeds 30 bps. The strategy is capacity-bound (order of ₹50–200 cr), not unlimited.
- **Execution** modeled at the rebalance close; slippage is folded into the cost rate.
- **Sector data** is a current snapshot (no point-in-time membership).
- **Fundamentals** are non-point-in-time and were deliberately *not* used.

---

## 8. Conclusion

On a clean, survivorship-free, corporate-action-adjusted, point-in-time Indian-equity panel,
a transparent composite of momentum, 52-week-high proximity, delivery strength, and low
volatility — held long-only with a breadth regime gate — produces a risk-adjusted return
(Sharpe ≈ 1.1–1.2, max drawdown ≈ −15%) that is stable across eras, survives out-of-sample
and multiple-testing scrutiny, and roughly doubles the benchmark Sharpe. The delivery and
low-volatility signals, and the regime gate, are the differentiated contributors. The result
is a capacity-bounded, implementable factor-tilt strategy — and a fully reproducible pipeline.

---

## Reproduce

```powershell
py -3.14 common\build_adjusted_prices.py     # adjusted prices
py -3.14 registry\build_isin_master.py        # ISIN master
py -3.14 registry\build_pit_universe.py       # equity-only PIT universe
py -3.14 common\build_feature_store.py        # features + IC
py -3.14 common\backtest_momentum.py          # flagship A
py -3.14 common\backtest_hardening.py          # robustness + DSR
py -3.14 common\backtest_multifactor.py        # 4-factor B + sector-neutral
py -3.14 common\fno_feature_study.py           # F&O signal study
py -3.14 common\verify_phases.py               # 29-check audit
py -3.14 common\generate_signals.py            # today's book + regime
```

---

## Part 1 — Idea Engine & Foundation Hardening (complete, 2026-07)

The "ultra-advanced" upgrade Part 1. Most of the doc's assumed "foundation gaps"
already existed (Parquet lake, DuckDB, PIT universe, adj/TR prices, feature store,
verify suite); Part 1 built the genuinely missing layer. See `MICC_UPGRADE_PART1.md`.

**Delivered**
- **Idea Engine** (`ideas/`): `thesis` / `trade` / `idea_card` model; 555 legacy
  recommendations backfilled with exact return parity.
- **ATR bands + auto timeframe**: live book → ATR-14 stop/target, swing vs positional
  (ADX≥25 & >200DMA), equal rupee-risk integer sizing; `atr_k` persisted per trade.
- **6-pillar versioned scorer**: `score_weights` (v1.0) + per-pillar `score_audit`;
  confidence fully reproducible from the audit. Fundamentals cap (A3): value/quality
  ≤70 until ≥8yr annual data (binds today — depth is ~5yr).
- **Named PIT index membership** (`index_membership`): hybrid — official current
  (100% NIFTY 50) + turnover-reconstructed history (confidence-flagged; NIFTY 50
  proxy is only ~58% accurate, not oversold).
- **Sector**: current top-500 gap closed (ETFs tagged); overall stays ~60% by design.
- **verify_phases.py**: 29 → **49 checks** (added P6 PIT/membership/sector, P7 backfill
  parity, P8 band invariants, P9 scoring reproducibility). All green.

**Reproduce Part 1**
```powershell
py -3.14 ideas\schema.py                        # idea/scoring tables
py -3.14 ideas\backfill_recommendations.py      # 555 recs -> thesis+trade
py -3.14 registry\build_index_membership.py     # named PIT membership
py -3.14 registry\backfill_top500_sectors.py    # top-500 sector coverage
py -3.14 ideas\build_idea_cards.py              # bands -> scoring -> cards (daily)
py -3.14 common\verify_phases.py                # 49-check audit
```

**Deferred:** Part 2 (populate real sub-scores: macro spine, events, signal library),
Part 3 (Friday learning loop updating `score_weights`, risk engine, ML/CPCV overlay).
