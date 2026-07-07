import { useEffect, useMemo, useRef, useState } from "react";
import { m } from "framer-motion";
import { EASE_OUT, stagger } from "../lib/motion";
import { reportFetch, subscribeFreshness, requestRefresh } from "../lib/freshness";

export function Glass({ children, className = "", hover = false, ...rest }) {
  return (
    <div className={`glass ${hover ? "glass-hover" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function Section({ title, sub, children, right }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-end justify-between">
        <div>
          <h2 className="label">{title}</h2>
          {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

/** animated count-up for hero numbers */
export function CountUp({ value, format = (v) => v.toFixed(2), duration = 1 }) {
  const [disp, setDisp] = useState(0);
  const start = useRef(null);
  const from = useRef(0);
  useEffect(() => {
    if (value == null) return;
    from.current = disp;
    start.current = null;
    let raf;
    const tick = (t) => {
      if (!start.current) start.current = t;
      const p = Math.min((t - start.current) / (duration * 1000), 1);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      setDisp(from.current + (value - from.current) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);
  if (value == null) return <span>—</span>;
  return <span className="num">{format(disp)}</span>;
}

export function Stat({ label, value, sub, format, accent = "text-slate-100" }) {
  return (
    <Glass hover className="flex-1 min-w-[140px] px-5 py-4">
      <div className={`text-2xl font-semibold tabular-nums ${accent}`}>
        {typeof value === "number" ? <CountUp value={value} format={format} /> : <span className="num">{value ?? "—"}</span>}
      </div>
      <div className="mt-1 text-xs text-slate-400">{label}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </Glass>
  );
}

export function Badge({ ok, children, pulse = false }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-medium border
        transition-colors duration-300
        ${ok ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
             : "border-red-500/40 text-red-300 bg-red-500/10"}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-red-400"} ${pulse ? "animate-pulse" : ""}`} />
      {children}
    </span>
  );
}

export function Pill({ children, tone = "slate" }) {
  const tones = {
    slate: "border-white/10 text-slate-300 bg-white/[0.03]",
    cyan: "border-cyan-500/30 text-cyan-300 bg-cyan-500/10",
    emerald: "border-emerald-500/30 text-emerald-300 bg-emerald-500/10",
    red: "border-red-500/30 text-red-300 bg-red-500/10",
    amber: "border-amber-500/30 text-amber-300 bg-amber-500/10",
    violet: "border-violet-500/30 text-violet-300 bg-violet-500/10",
  };
  return <span className={`rounded-md border px-2 py-0.5 text-[11px] leading-relaxed ${tones[tone]}`}>{children}</span>;
}

/**
 * Table — optionally searchable/sortable. Both are opt-in and fully backward
 * compatible: omit sortAccessors/searchKeys and it behaves exactly as before.
 *   sortAccessors: array parallel to cols, entry = (row) => comparable value,
 *                  or null/undefined for a non-sortable column.
 *   searchKeys:    array of (row) => string, joined into the search haystack.
 */
export function Table({ cols, rows, render, sortAccessors, searchKeys, animateRows = true }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState(null); // { i: colIndex, dir: 1|-1 }

  const filtered = useMemo(() => {
    if (!q || !searchKeys?.length) return rows;
    const needle = q.toLowerCase();
    return rows.filter((r) => searchKeys.some((fn) => String(fn(r) ?? "").toLowerCase().includes(needle)));
  }, [rows, q, searchKeys]);

  const sorted = useMemo(() => {
    if (!sort || !sortAccessors?.[sort.i]) return filtered;
    const acc = sortAccessors[sort.i];
    return [...filtered].sort((a, b) => {
      const av = acc(a), bv = acc(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
  }, [filtered, sort, sortAccessors]);

  const toggleSort = (i) => setSort((s) => (s?.i === i ? { i, dir: -s.dir } : { i, dir: 1 }));

  return (
    <div>
      {searchKeys?.length > 0 && (
        <div className="mb-2 flex items-center justify-between px-1">
          <div className="relative">
            <SearchIcon />
            <input
              aria-label="Search table"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="w-56 rounded-lg border border-white/10 bg-white/[0.03] py-1.5 pl-8 pr-3 text-[12px]
                         text-slate-200 placeholder:text-slate-500 outline-none transition-colors
                         focus:border-cyan-500/40 focus:bg-white/[0.05]"
            />
          </div>
          {q && <span className="text-[11px] text-slate-500">{sorted.length} of {rows.length}</span>}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-slate-500">
              {cols.map((c, i) => {
                const canSort = !!sortAccessors?.[i];
                const ariaSort = sort?.i === i ? (sort.dir === -1 ? "descending" : "ascending") : canSort ? "none" : undefined;
                return (
                  <th key={c} aria-sort={ariaSort}
                      className="border-b border-white/10 px-3 py-2 font-medium">
                    {canSort ? (
                      <button
                        onClick={() => toggleSort(i)}
                        className="inline-flex items-center gap-1 select-none transition-colors hover:text-slate-300"
                      >
                        {c}
                        <span aria-hidden="true" className={`text-[9px] transition-opacity ${sort?.i === i ? "opacity-100 text-cyan-300" : "opacity-30"}`}>
                          {sort?.i === i && sort.dir === -1 ? "▼" : "▲"}
                        </span>
                      </button>
                    ) : c}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => {
              const cells = render(r).map((cell, j) => (
                <td key={j} className="px-3 py-2 whitespace-nowrap">{cell}</td>
              ));
              return animateRows ? (
                <m.tr
                  key={i}
                  {...stagger(i, { delay: 0.012, cap: 0.35, y: 3 })}
                  className="border-b border-white/[0.04] transition-colors duration-150 hover:bg-white/[0.03]"
                >
                  {cells}
                </m.tr>
              ) : (
                <tr key={i} className="border-b border-white/[0.04] transition-colors duration-150 hover:bg-white/[0.03]">
                  {cells}
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr><td colSpan={cols.length} className="px-3 py-8 text-center text-slate-500">no matches</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── skeleton loading states — shaped to match what's actually loading,
   replacing a single generic spinner used identically on every page ── */

export function Skeleton({ className = "" }) {
  return <div className={`skeleton ${className}`} />;
}

export function StatSkeleton({ n = 4 }) {
  return (
    <div className="flex flex-wrap gap-4">
      {Array.from({ length: n }).map((_, i) => (
        <Glass key={i} className="flex-1 min-w-[140px] px-5 py-4">
          <Skeleton className="h-7 w-20" />
          <Skeleton className="mt-2 h-3 w-24" />
        </Glass>
      ))}
    </div>
  );
}

export function CardGridSkeleton({ n = 6 }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: n }).map((_, i) => (
        <Glass key={i} className="p-4">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-3 w-28" />
            </div>
            <Skeleton className="h-11 w-11 rounded-full" />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            <Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" />
          </div>
          <div className="mt-3 flex gap-1.5">
            <Skeleton className="h-5 w-14" /><Skeleton className="h-5 w-14" /><Skeleton className="h-5 w-16" />
          </div>
        </Glass>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 4 }) {
  return (
    <Glass className="p-3">
      <div className="space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4">
            {Array.from({ length: cols }).map((_, j) => (
              <Skeleton key={j} className={`h-4 ${j === 0 ? "w-32" : "w-16"}`} />
            ))}
          </div>
        ))}
      </div>
    </Glass>
  );
}

export function ChartSkeleton({ height = 340 }) {
  return (
    <Glass className="p-4">
      <Skeleton className="w-full" style={{ height }} />
    </Glass>
  );
}

/** generic page loader — falls back to a spinner when no shape is a better fit */
export function Loading() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500/30 border-t-cyan-400" />
    </div>
  );
}

export function ErrorState({ error, retry }) {
  return (
    <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, ease: EASE_OUT }}
      className="flex h-64 flex-col items-center justify-center gap-3 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10 text-red-300">
        !
      </div>
      <div className="text-sm text-slate-300">Couldn't load this data.</div>
      <div className="max-w-xs text-[12px] text-slate-500">{String(error?.message || error || "Unknown error")}</div>
      {retry && (
        <button onClick={retry}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-[12px] text-slate-300 transition-colors hover:bg-white/5">
          Retry
        </button>
      )}
    </m.div>
  );
}

export function useApi(fetcher) {
  const [state, setState] = useState({ data: null, err: null, fetchedAt: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    fetcher()
      .then((data) => {
        if (!live) return;
        reportFetch();
        setState({ data, err: null, fetchedAt: Date.now() });
      })
      .catch((err) => live && setState((s) => ({ ...s, err })));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);
  // a global "Refresh" click (see FreshnessBar) bumps every mounted useApi at
  // once -- the only way stale-but-still-open pages ever get new data, since
  // there's no polling and api() no longer caches.
  useEffect(() => {
    const onRefresh = () => setTick((t) => t + 1);
    window.addEventListener("micc:refresh", onRefresh);
    return () => window.removeEventListener("micc:refresh", onRefresh);
  }, []);
  return { ...state, retry: () => setTick((t) => t + 1) };
}

function relTime(ts) {
  if (!ts) return null;
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

/** Global "last updated / Refresh" pill -- mounted once in Layout. Tracks the
 * most recent successful fetch app-wide and lets you force every currently
 * mounted page's data to refetch, since nothing here auto-polls. */
export function FreshnessBar() {
  const [at, setAt] = useState(null);
  const [, setTock] = useState(0);
  useEffect(() => subscribeFreshness(setAt), []);
  useEffect(() => {
    const id = setInterval(() => setTock((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <button
      onClick={requestRefresh}
      title="Refetch this page's data"
      className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1
                 text-[11px] text-slate-500 transition-colors hover:border-white/20 hover:text-slate-300"
    >
      <span aria-hidden="true">↻</span>
      <span>{at ? `Updated ${relTime(at)}` : "Refresh"}</span>
    </button>
  );
}

export const tooltipStyle = {
  backgroundColor: "#101b30",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  fontSize: 12,
  fontFamily: "Cascadia Mono, monospace",
  color: "#e2e8f0",
  boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
};

export function SearchIcon() {
  return (
    <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
         strokeLinecap="round" strokeLinejoin="round"
         className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500">
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}
