// Minimal but structurally real payloads, shaped like the actual /api/* responses
// (confirmed live via curl during the ops session), so page smoke tests exercise
// the real field access patterns instead of an imagined shape.

export const mockRegime = { date: "2026-07-06", pct_above_200dma: 44, pct_above_50dma: 40 };

export const mockRiskCurrent = {
  as_of_date: "2026-07-06", equity: 466937.44, drawdown_pct: 0.0388,
  risk_budget_mult: 1.0, consec_losses: 0, avg_pairwise_corr: 0.204,
  halt_new_cards: 0, regime_votes: 2, notes: "R-based desk curve",
  sector_concentration_json: JSON.stringify({ Healthcare: 0.29, Financials: 0.23 }),
};
export const mockRisk = { current: mockRiskCurrent, history: [mockRiskCurrent] };

export const mockBest = { series: [{ date: "2026-01-01", equity: 1.2, drawdown: -0.05 }] };

export const mockIdeaCard = {
  symbol: "RELIANCE", company: "Reliance Industries", confidence_score: 68,
  entry: 2500, stop: 2400, target: 2700, timeframe_class: "positional",
  rr_ratio: 2.0, size_shares: 10, sector: "Energy", in_book: 1,
  pillars: { signal_strength: { contribution: 5, subscore: 70, weight: 0.35 } },
  context: { regime_spine: "neutral" },
  // lifecycle enrichment
  issue_date: "2026-06-25", target_date: "2026-09-21", horizon_td: 63,
  days_left: 76, days_held: 12, profit_target_pct: 0.08, stop_risk_pct: -0.04,
  current_price: 2560, price_as_of: "2026-07-07", current_pl_pct: 0.024, target_progress: 0.30,
};
export const mockIdeas = { cards: [mockIdeaCard], n: 1, card_date: "2026-07-06" };

export const mockStrategies = [{ strategy: "LO + Regime gate", Sharpe: 1.4, CAGR: 0.22, MaxDD: -0.18, Calmar: 1.2 }];
export const mockHealth = { streak: 30, target: 30 };

export const mockVerdicts = {
  preregistration: [{ signal: "amihud", status: "context", test: "rank-IC", notes: "IC -0.02" }],
  candidates: [{ candidate: "amihud", mean_ic: -0.02, t_stat: -1.1, ic_h1: -0.01, ic_h2: -0.03, verdict: "context" }],
  events: [{ event_type: "buyback", mean_ar: 0.01, t_stat: 1.2, n_events: 20, verdict: "context" }],
  spine: [{ book: "IV", sharpe_spine: 1.4, sharpe_incumbent: 1.3, shipped: true }],
  ml_experiments: [{ exp_id: "e1", model_family: "gbm", status: "context" }],
  ml_paths: [{ model: "gbm", sharpe: 1.1 }],
  exit_calibration: [{ variant: "atr2x", exp_r_train: 0.3, exp_r_test: 0.28, hit_rate_test: 0.5, stop_rate_test: 0.3, mfe_capture_test: 0.6, verdict: "KEEP" }],
};
export const mockReview = { latest: null, weights: [] };

export const mockFunds = [{ scheme_name: "Test Fund", amc: "Test Mutual Fund", cat_short: "Large Cap", cagr_3y: 0.18, sharpe_3y: 1.1, max_dd: -0.15 }];

export const mockEvents = {
  recent: [{ event_date: "2026-07-01", symbol: "TCS", event_type: "insider_buy", evidence_tier: "scored" }],
  shadow: [{ event_type: "insider_buy", n: 50, filled63: 30, hit63: 0.55, avg63: 0.03 }],
  tags: [{ tag: "capex", n: 120 }],
};
