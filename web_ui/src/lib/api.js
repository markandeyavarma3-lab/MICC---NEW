// Thin fetch layer over the MICC Python API (same origin in prod; vite proxy in dev).
// Deliberately no caching here: the backend queries the live DB per-request, and
// this desk gets checked repeatedly through the day -- a permanent cache meant
// "Desk R-PnL"/"Drawdown" could silently go stale for an entire tab session with
// no way to tell. Freshness is manual (see lib/freshness.js): pages refetch on
// mount and on an explicit user-triggered refresh, never on a timer.
export async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

// categorical palette — validated (dataviz six checks, dark surface #0a1222)
export const C = {
  cyan: "#0891b2",
  emerald: "#059669",
  violet: "#7c3aed",
  amber: "#d97706",
  // status (reserved, never series colors)
  good: "#10b981",
  bad: "#ef4444",
  ink: "#e2e8f0",
  muted: "#64748b",
};

export const fmt = {
  inr: (v) => (v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })),
  lakh: (v) => (v == null ? "—" : "₹" + (v / 1e5).toFixed(1) + "L"),
  pct: (v, d = 1) => (v == null ? "—" : (v * 100).toFixed(d) + "%"),
  pctSigned: (v, d = 1) => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%"),
  num: (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d)),
  x: (v) => (v == null ? "—" : Number(v).toFixed(0) + "x"),
};
