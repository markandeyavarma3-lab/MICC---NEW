import { useEffect, useRef, useState } from "react";
import { m, AnimatePresence } from "framer-motion";
import { api, fmt } from "../lib/api";
import { Glass, Pill, Skeleton } from "./ui";
import { useSymbol } from "../lib/symbolContext";
import { EASE_OUT, springDrawer } from "../lib/motion";
import { useFocusTrap } from "../lib/a11y";

/** Unified per-symbol profile: asset features + a live idea card summary (if
 * one exists) + recent events — composed client-side from endpoints that
 * already exist (/api/asset, /api/ideas, /api/events), no new backend needed.
 * Mounted once at the app shell; any page opens it via useSymbol().open(sym). */
export default function SymbolDrawer() {
  const { symbol, close } = useSymbol();
  return (
    <AnimatePresence>
      {symbol && <DrawerBody key={symbol} symbol={symbol} onClose={close} />}
    </AnimatePresence>
  );
}

function DrawerBody({ symbol, onClose }) {
  const [asset, setAsset] = useState(undefined); // undefined = loading, null = 404
  const [idea, setIdea] = useState(null);
  const [events, setEvents] = useState([]);
  const panelRef = useRef(null);
  useFocusTrap(panelRef, true);

  useEffect(() => {
    let live = true;
    api(`/api/asset/${symbol}`).then((d) => live && setAsset(d)).catch(() => live && setAsset(null));
    api("/api/ideas").then((d) => {
      if (!live) return;
      setIdea(d?.cards?.find((c) => c.symbol === symbol) || null);
    }).catch(() => {});
    api("/api/events").then((d) => {
      if (!live) return;
      setEvents((d?.recent || []).filter((e) => e.symbol === symbol).slice(0, 8));
    }).catch(() => {});
    return () => { live = false; };
  }, [symbol]);

  // Esc to close
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const feat = asset?.latest_features;

  return (
    <>
      <m.div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
        onClick={onClose}
      />
      <m.aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`${symbol} profile`}
        className="fixed right-0 top-0 z-50 h-full w-[440px] overflow-y-auto border-l border-white/10 bg-navy-900/95 p-6 backdrop-blur-2xl"
        initial={{ x: 460 }} animate={{ x: 0 }} exit={{ x: 460 }}
        transition={springDrawer}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xl font-bold text-slate-100">{symbol}</div>
            <div className="text-xs text-slate-500">{asset?.sector || (asset === null ? "no data on file" : <Skeleton className="mt-1 inline-block h-3 w-24 align-middle" />)}</div>
          </div>
          <m.button whileTap={{ scale: 0.92 }} onClick={onClose} aria-label="Close"
            className="rounded-lg border border-white/10 px-2.5 py-1 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200">✕</m.button>
        </div>

        {asset === undefined && (
          <div className="mt-6 space-y-3">
            <Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" />
          </div>
        )}

        {asset === null && (
          <div className="mt-6 text-sm text-slate-500">
            No feature/fundamental data on file for this symbol (may be outside the liquid universe, an ETF/fund, or delisted).
          </div>
        )}

        {idea && (
          <div className="mt-6">
            <div className="label mb-2">Live idea card</div>
            <Glass className="p-4">
              <div className="flex items-center justify-between">
                <div className="text-2xl font-semibold text-slate-100">{idea.confidence_score.toFixed(1)}</div>
                <Pill tone={idea.in_book === 0 ? "amber" : "emerald"}>{idea.in_book === 0 ? "waitlist" : "in book"}</Pill>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[12px]">
                <div><div className="num text-slate-200">{fmt.inr(idea.entry)}</div><div className="text-[10px] uppercase tracking-wider text-slate-500">entry</div></div>
                <div><div className="num text-red-300">{fmt.inr(idea.stop)}</div><div className="text-[10px] uppercase tracking-wider text-slate-500">stop</div></div>
                <div><div className="num text-emerald-300">{fmt.inr(idea.target)}</div><div className="text-[10px] uppercase tracking-wider text-slate-500">target</div></div>
              </div>
              <div className="mt-3 text-center text-[11px] text-slate-500">see Idea Cards for the full pillar breakdown</div>
            </Glass>
          </div>
        )}

        {feat && (
          <div className="mt-6">
            <div className="label mb-2">Latest features · {feat.rebal_date}</div>
            <Glass className="grid grid-cols-2 gap-3 p-4 text-[13px]">
              <Kv k="12-1 momentum" v={fmt.pct(feat.mom_12_1)} />
              <Kv k="6-1 momentum" v={fmt.pct(feat.mom_6_1)} />
              <Kv k="52w high proximity" v={fmt.pct(feat.prox_52w_high)} />
              <Kv k="Dist. SMA200" v={fmt.pct(feat.dist_sma200)} />
              <Kv k="Vol (3m)" v={fmt.pct(feat.vol_3m)} />
              <Kv k="Delivery (1m)" v={fmt.num(feat.deliv_1m, 1) + "%"} />
            </Glass>
          </div>
        )}

        {asset?.fundamentals && (
          <div className="mt-6">
            <div className="label mb-2">Fundamentals · {asset.fundamentals.report_date}</div>
            <Glass className="grid grid-cols-2 gap-3 p-4 text-[13px]">
              <Kv k="EPS" v={"₹" + fmt.num(asset.fundamentals.eps)} />
              <Kv k="ROE" v={fmt.pct(asset.fundamentals.roe)} />
            </Glass>
          </div>
        )}

        {events.length > 0 && (
          <div className="mt-6">
            <div className="label mb-2">Recent events</div>
            <Glass className="p-3">
              {events.map((e, i) => (
                <div key={i} className="flex items-center justify-between border-b border-white/[0.04] py-2 text-[12px] last:border-0">
                  <span className="num text-slate-500">{e.event_date}</span>
                  <span className="text-slate-300">{e.event_type}</span>
                  <Pill tone={e.evidence_tier === "scored" ? "emerald" : "slate"}>{e.evidence_tier}</Pill>
                </div>
              ))}
            </Glass>
          </div>
        )}
      </m.aside>
    </>
  );
}

function Kv({ k, v }) {
  return (
    <div>
      <div className="num text-slate-200">{v}</div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
    </div>
  );
}
