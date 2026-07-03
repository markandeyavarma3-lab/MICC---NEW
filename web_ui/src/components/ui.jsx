import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

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
          <h2 className="text-[13px] font-semibold uppercase tracking-[0.14em] text-slate-400">{title}</h2>
          {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

/** animated count-up for hero numbers */
export function CountUp({ value, format = (v) => v.toFixed(2), duration = 0.9 }) {
  const [disp, setDisp] = useState(0);
  const start = useRef(null);
  useEffect(() => {
    if (value == null) return;
    let raf;
    const tick = (t) => {
      if (!start.current) start.current = t;
      const p = Math.min((t - start.current) / (duration * 1000), 1);
      setDisp(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  if (value == null) return <span>—</span>;
  return <span className="num">{format(disp)}</span>;
}

export function Stat({ label, value, sub, format, accent = "text-slate-100" }) {
  return (
    <Glass hover className="flex-1 min-w-[140px] px-5 py-4">
      <div className={`text-2xl font-semibold ${accent}`}>
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
  return <span className={`rounded-md border px-2 py-0.5 text-[11px] ${tones[tone]}`}>{children}</span>;
}

export function Table({ cols, rows, render }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-left text-slate-500">
            {cols.map((c) => (
              <th key={c} className="border-b border-white/10 px-3 py-2 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr
              key={i}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.015, 0.4) }}
              className="border-b border-white/[0.04] hover:bg-white/[0.03]"
            >
              {render(r).map((cell, j) => (
                <td key={j} className="px-3 py-2 whitespace-nowrap">{cell}</td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Loading() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500/30 border-t-cyan-400" />
    </div>
  );
}

export function useApi(fetcher) {
  const [state, setState] = useState({ data: null, err: null });
  useEffect(() => {
    let live = true;
    fetcher()
      .then((data) => live && setState({ data, err: null }))
      .catch((err) => live && setState({ data: null, err }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return state;
}

export const tooltipStyle = {
  backgroundColor: "#101b30",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  fontSize: 12,
  fontFamily: "Cascadia Mono, monospace",
  color: "#e2e8f0",
};
