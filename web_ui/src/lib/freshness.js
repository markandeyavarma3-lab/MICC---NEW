// Tracks the most recent successful API fetch across the whole app, and lets
// any control (the Layout refresh pill) force every currently-mounted useApi()
// to refetch on demand -- the "manual refresh" half of the freshness fix.
const listeners = new Set();
let lastFetchAt = null;

export function reportFetch() {
  lastFetchAt = Date.now();
  listeners.forEach((fn) => fn(lastFetchAt));
}

export function subscribeFreshness(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getLastFetchAt() {
  return lastFetchAt;
}

export function requestRefresh() {
  window.dispatchEvent(new Event("micc:refresh"));
}
