// Thin fetch layer over the MICC Python API (same origin in prod; vite proxy in dev).
const cache = new Map();

export async function api(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  const data = await res.json();
  cache.set(path, data);
  return data;
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
  num: (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d)),
  x: (v) => (v == null ? "—" : Number(v).toFixed(0) + "x"),
};
