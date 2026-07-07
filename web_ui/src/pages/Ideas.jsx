import { useEffect, useRef, useState } from "react";
import { m, AnimatePresence } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from "recharts";
import { api, C, fmt } from "../lib/api";
import { Glass, Section, Pill, useApi, tooltipStyle, CardGridSkeleton, ErrorState } from "../components/ui";
import { EASE_OUT, springDrawer, stagger } from "../lib/motion";
import { useFocusTrap } from "../lib/a11y";

const PILLAR_ORDER = ["signal_strength", "trend_align", "regime_align", "confirmation",
                      "liquidity_capacity", "event_score", "risk_penalty"];

export default function Ideas() {
  const ideas = useApi(() => api("/api/ideas"));
  const [open, setOpen] = useState(null); // selected card

  if (ideas.err) return <ErrorState error={ideas.err} retry={ideas.retry} />;
  if (!ideas.data) {
    return (
      <Section title="Idea cards" sub="loading…">
        <CardGridSkeleton />
      </Section>
    );
  }
  const { cards, card_date, n } = ideas.data;

  return (
    <>
      <Section title="Idea cards" sub={`${n} live · ${card_date} · ATR bands, stop ≤10%, equal rupee-risk · click a card for the full thesis`}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((c, i) => {
            const st = stagger(i, { delay: 0.025, cap: 0.5 });
            return (
            <m.div key={c.symbol} layoutId={`idea-card-${c.symbol}`}
                        initial={st.initial} animate={st.animate}
                        transition={{ ...st.transition, layout: springDrawer }}
                        whileTap={{ scale: 0.985 }} className="select-none">
              <Glass hover className="cursor-pointer p-4" onClick={() => setOpen(c)}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-[15px] font-semibold text-slate-100">{c.symbol}</div>
                    <div className="mt-0.5 max-w-[190px] truncate text-[11px] text-slate-500">{c.company}</div>
                  </div>
                  <ConfRing v={c.confidence_score} />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <Kv k="entry" v={fmt.inr(c.entry)} />
                  <Kv k="stop" v={fmt.inr(c.stop)} tone="text-red-300" />
                  <Kv k="target" v={fmt.inr(c.target)} tone="text-emerald-300" />
                </div>

                {/* lifecycle: live P/L vs. the fixed profit target, + days-left countdown */}
                <div className="mt-3 flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">current P/L</div>
                    <div className={`num text-[13px] font-semibold ${plTone(c.current_pl_pct)}`}>
                      {c.current_pl_pct != null ? fmt.pctSigned(c.current_pl_pct) : "—"}
                    </div>
                  </div>
                  <TargetMeter c={c} />
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">days left</div>
                    <div className={`num text-[13px] font-semibold ${c.days_left != null && c.days_left < 0 ? "text-amber-300" : "text-slate-200"}`}>
                      {c.days_left != null ? (c.days_left < 0 ? "elapsed" : c.days_left) : "—"}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Pill tone={c.timeframe_class === "positional" ? "violet" : "cyan"}>{c.timeframe_class}</Pill>
                  <Pill tone="emerald">tgt {c.profit_target_pct != null ? fmt.pctSigned(c.profit_target_pct) : "—"}</Pill>
                  <Pill tone="slate">R:R {fmt.num(c.rr_ratio, 1)}</Pill>
                  {c.sector && <Pill tone="slate">{c.sector}</Pill>}
                  <Pill tone={c.in_book === 0 ? "amber" : "emerald"}>{c.in_book === 0 ? "waitlist" : "in book"}</Pill>
                </div>
              </Glass>
            </m.div>
            );
          })}
        </div>
      </Section>

      {/* ===== drill-down drawer ===== */}
      <AnimatePresence>
        {open && <ThesisDrawer card={open} onClose={() => setOpen(null)} />}
      </AnimatePresence>
    </>
  );
}

function Kv({ k, v, tone = "text-slate-200" }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-1 py-1.5">
      <div className={`num text-[13px] font-medium ${tone}`}>{v}</div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
    </div>
  );
}

const plTone = (v) => (v == null ? "text-slate-400" : v > 0 ? "text-emerald-300" : v < 0 ? "text-red-300" : "text-slate-200");

function LcRow({ k, v, sub, tone = "text-slate-200" }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
      <div className={`num font-medium ${tone}`}>{v}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

/** Tiny horizontal meter: how far current price has travelled from entry (0)
 * toward the profit target (1). Clamped 0..1 for the bar; can read <0 (underwater)
 * or >1 (past target) in the number, which the card shows separately. */
function TargetMeter({ c }) {
  const p = c.target_progress;
  const clamped = p == null ? 0 : Math.max(0, Math.min(1, p));
  return (
    <div className="mx-3 flex-1">
      <div className="mb-1 text-center text-[10px] uppercase tracking-wider text-slate-500">
        to target {p != null ? `${Math.round(p * 100)}%` : "—"}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className={`h-full rounded-full ${p != null && p < 0 ? "bg-red-400/70" : "bg-cyan-400/70"}`}
             style={{ width: `${clamped * 100}%` }} />
      </div>
    </div>
  );
}

function ConfRing({ v }) {
  const r = 17, circ = 2 * Math.PI * r;
  const tone = v >= 65 ? "#10b981" : v >= 55 ? "#0891b2" : "#d97706";
  return (
    <div className="relative h-11 w-11">
      <svg viewBox="0 0 44 44" className="h-11 w-11 -rotate-90">
        <circle cx="22" cy="22" r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="4" />
        <m.circle
          cx="22" cy="22" r={r} fill="none" stroke={tone} strokeWidth="4" strokeLinecap="round"
          initial={{ strokeDasharray: circ, strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - v / 100) }}
          transition={{ duration: 1, ease: EASE_OUT, delay: 0.1 }}
        />
      </svg>
      <span className="num absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-slate-200">
        {v.toFixed(0)}
      </span>
    </div>
  );
}

function ThesisDrawer({ card, onClose }) {
  const pillars = PILLAR_ORDER
    .filter((p) => card.pillars?.[p])
    .map((p) => ({ name: p.replace(/_/g, " "), contribution: card.pillars[p].contribution,
                   subscore: card.pillars[p].subscore, weight: card.pillars[p].weight }));

  const range = { lo: card.stop, hi: card.target, entry: card.entry };
  const pct = (v) => ((v - range.lo) / (range.hi - range.lo)) * 100;

  const panelRef = useRef(null);
  useFocusTrap(panelRef, true);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
        aria-label={`${card.symbol} thesis`}
        layoutId={`idea-card-${card.symbol}`}
        transition={{ layout: springDrawer }}
        className="fixed right-0 top-0 z-50 h-full w-[480px] overflow-y-auto border-l border-white/10 bg-navy-900/95 p-6 backdrop-blur-2xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xl font-bold text-slate-100">{card.symbol}</div>
            <div className="text-xs text-slate-500">{card.company} · {card.sector || "—"}</div>
          </div>
          <m.button whileTap={{ scale: 0.92 }} onClick={onClose} aria-label="Close"
            className="rounded-lg border border-white/10 px-2.5 py-1 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200">✕</m.button>
        </div>

        {/* the card only shows symbol/entry/stop/target -- everything else here
            is new to the drawer, so it fades in rather than popping instantly
            while the shared-layout box is still morphing from the card */}
        <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: 0.12 }}>
        <div className="mt-4 flex gap-2">
          <Pill tone={card.timeframe_class === "positional" ? "violet" : "cyan"}>{card.timeframe_class}</Pill>
          <Pill tone="slate">momentum · {card.size_shares} shares</Pill>
          <Pill tone={card.in_book === 0 ? "amber" : "emerald"}>{card.in_book === 0 ? "waitlist" : "in book"}</Pill>
        </div>

        {/* price band visual */}
        <div className="mt-6">
          <div className="mb-1.5 flex justify-between text-[11px] text-slate-500">
            <span className="num text-red-300">{fmt.inr(card.stop)} stop</span>
            <span className="num text-emerald-300">target {fmt.inr(card.target)}</span>
          </div>
          <div className="relative h-2.5 rounded-full bg-gradient-to-r from-red-500/40 via-white/10 to-emerald-500/40">
            <m.div
              className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-white bg-cyan-500 shadow-[0_0_12px_rgba(8,145,178,.8)]"
              initial={{ left: 0 }} animate={{ left: `calc(${pct(range.entry)}% - 8px)` }}
              transition={{ duration: 0.9, ease: EASE_OUT, delay: 0.15 }}
            />
          </div>
          <div className="mt-1.5 text-center text-[11px] text-slate-400">
            entry <span className="num text-slate-200">{fmt.inr(card.entry)}</span> · R:R {fmt.num(card.rr_ratio, 1)}:1
          </div>
        </div>

        {/* lifecycle detail — dates, countdown, live P/L vs. targets */}
        <div className="mt-6">
          <div className="label mb-2">Lifecycle</div>
          <Glass className="p-3">
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
              <LcRow k="Date issued" v={card.issue_date || "—"} />
              <LcRow k="Target date" v={card.target_date || "—"} />
              <LcRow k="Days held" v={card.days_held != null ? `${card.days_held}d` : "—"} />
              <LcRow k="Days left"
                     v={card.days_left != null ? (card.days_left < 0 ? "elapsed" : `${card.days_left}d`) : "—"}
                     tone={card.days_left != null && card.days_left < 0 ? "text-amber-300" : "text-slate-200"} />
              <LcRow k="Profit target"
                     v={card.profit_target_pct != null ? fmt.pctSigned(card.profit_target_pct) : "—"}
                     tone="text-emerald-300" />
              <LcRow k="Stop risk"
                     v={card.stop_risk_pct != null ? fmt.pctSigned(card.stop_risk_pct) : "—"}
                     tone="text-red-300" />
              <LcRow k="Current price"
                     v={card.current_price != null ? `${fmt.inr(card.current_price)}` : "—"}
                     sub={card.price_as_of ? `as of ${card.price_as_of}` : undefined} />
              <LcRow k="Current P/L"
                     v={card.current_pl_pct != null ? fmt.pctSigned(card.current_pl_pct) : "—"}
                     tone={plTone(card.current_pl_pct)}
                     sub={card.target_progress != null ? `${Math.round(card.target_progress * 100)}% to target` : undefined} />
            </div>
          </Glass>
        </div>

        {/* pillar waterfall */}
        <div className="mt-7">
          <div className="label mb-2">
            Why {card.confidence_score.toFixed(1)} — pillar contributions (exact, linear)
          </div>
          <Glass className="p-3">
            <ResponsiveContainer width="100%" height={pillars.length * 34 + 20}>
              <BarChart data={pillars} layout="vertical" margin={{ top: 4, right: 40, bottom: 0, left: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v, _n, p) => [`${v > 0 ? "+" : ""}${v.toFixed(2)} (sub ${p.payload.subscore} × w ${p.payload.weight})`, "contribution"]}
                />
                <ReferenceLine x={0} stroke="rgba(255,255,255,.15)" />
                <Bar dataKey="contribution" radius={[4, 4, 4, 4]} barSize={14}
                     animationDuration={700} animationEasing="ease-out"
                     label={{ position: "right", fill: "#94a3b8", fontSize: 11,
                              formatter: (v) => (v > 0 ? "+" : "") + v.toFixed(1) }}>
                  {pillars.map((p, i) => (
                    <Cell key={i} fill={p.contribution >= 0 ? C.emerald : C.bad} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Glass>
        </div>

        {/* context tags (zero weight) */}
        {card.context && Object.keys(card.context).length > 0 && (
          <div className="mt-6">
            <div className="label mb-2">Context (display-only, zero weight)</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(card.context).map(([k, v]) => (
                <Pill key={k} tone="slate">{k.replace(/_/g, " ")}: {String(v)}</Pill>
              ))}
            </div>
          </div>
        )}

        <div className="mt-8 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-3 text-[11px] leading-relaxed text-amber-200/80">
          Confidence is a transparent heuristic composite, not a return forecast. Only the momentum
          edge is OOS-proven. Research only — not advice.
        </div>
        </m.div>
      </m.aside>
    </>
  );
}
