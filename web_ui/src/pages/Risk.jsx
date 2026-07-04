import { motion } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { api, C, fmt } from "../lib/api";
import { Glass, Section, Stat, Pill, useApi, tooltipStyle, StatSkeleton, ChartSkeleton, ErrorState } from "../components/ui";
import { springPill } from "../lib/motion";

const BRAKES = [
  { band: "DD < 10%", mult: "×1.00" },
  { band: "10 – 15%", mult: "×0.75" },
  { band: "15 – 22%", mult: "×0.50" },
  { band: "> 22%", mult: "×0.25 + HALT" },
];

export default function Risk() {
  const risk = useApi(() => api("/api/risk"));
  const ideas = useApi(() => api("/api/ideas"));
  if (risk.err) return <ErrorState error={risk.err} retry={risk.retry} />;
  if (!risk.data) {
    return (
      <>
        <StatSkeleton n={5} />
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ChartSkeleton height={200} /><ChartSkeleton height={200} />
        </div>
      </>
    );
  }
  const rc = risk.data.current || {};
  const conc = JSON.parse(rc.sector_concentration_json || "{}");
  const concData = Object.entries(conc).map(([sector, share]) => ({ sector, share }));
  const deployed = ideas.data
    ? ideas.data.cards.filter((c) => c.in_book !== 0).reduce((a, c) => a + (c.notional || 0), 0) : null;

  const ddBand = rc.drawdown_pct < 0.10 ? 0 : rc.drawdown_pct < 0.15 ? 1 : rc.drawdown_pct < 0.22 ? 2 : 3;

  return (
    <>
      <Section title="Risk state" sub={`as of ${rc.as_of_date || "—"} · governance, not alpha — brakes cap the tail, they don't predict`}>
        <div className="flex flex-wrap gap-4">
          <Stat label="Desk R-PnL (cumulative)" value={rc.equity} format={(v) => "₹" + (v / 1e5).toFixed(1) + "L"} accent="text-emerald-300" />
          <Stat label="Drawdown" value={rc.drawdown_pct} format={(v) => (v * 100).toFixed(1) + "%"} accent={ddBand > 0 ? "text-amber-300" : "text-slate-100"} />
          <Stat label="Risk budget" value={`×${rc.risk_budget_mult}`} sub={rc.halt_new_cards ? "HALTED" : "normal"} accent={rc.risk_budget_mult < 1 ? "text-amber-300" : "text-slate-100"} />
          <Stat label="Loss streak" value={rc.consec_losses} format={(v) => v.toFixed(0)} sub="brake at 3" />
          <Stat label="Deployed" value={deployed} format={(v) => "₹" + (v / 1e5).toFixed(1) + "L"} sub="of ₹1.0Cr" accent="text-cyan-300" />
        </div>
      </Section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section title="Drawdown brake ladder" sub="hard thresholds, verify-enforced">
          <Glass className="p-4">
            {BRAKES.map((b, i) => (
              <div key={b.band}
                   className={`relative mb-2 flex items-center justify-between rounded-xl border border-transparent px-4 py-3 text-[13px] transition-colors duration-300
                     ${i === ddBand ? "text-slate-100" : "text-slate-400"}`}>
                {i === ddBand && (
                  <motion.div layoutId="dd-band" className="absolute inset-0 rounded-xl border border-cyan-500/40 bg-cyan-500/10"
                              transition={springPill} />
                )}
                {i !== ddBand && <div className="absolute inset-0 rounded-xl border border-white/[0.06]" />}
                <span className="relative z-10">{b.band}</span>
                <span className="relative z-10 num font-medium">{b.mult}</span>
                {i === ddBand && <Pill tone="cyan">current</Pill>}
              </div>
            ))}
            <div className="mt-3 text-[11px] text-slate-500">
              plus: 3 consecutive losers → ×0.75 until a winner · holdings corr &gt;0.6 → throttle ·
              regime risk-off → fewer new cards
            </div>
          </Glass>
        </Section>

        <Section title="Sector concentration" sub="share of in-book notional">
          <Glass className="p-4">
            {concData.length ? (
              <ResponsiveContainer width="100%" height={concData.length * 36 + 16}>
                <BarChart data={concData} layout="vertical" margin={{ top: 4, right: 48, bottom: 0, left: 8 }}>
                  <XAxis type="number" hide domain={[0, Math.max(0.35, ...concData.map((d) => d.share))]} />
                  <YAxis type="category" dataKey="sector" width={150} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => [fmt.pct(v, 1), "share"]} />
                  <Bar dataKey="share" radius={[4, 4, 4, 4]} barSize={16}
                       animationDuration={700} animationEasing="ease-out"
                       label={{ position: "right", fill: "#94a3b8", fontSize: 11, formatter: (v) => (v * 100).toFixed(0) + "%" }}>
                    {concData.map((d, i) => (
                      <Cell key={i} fill={d.share > 0.30 ? C.amber : C.cyan} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="py-10 text-center text-sm text-slate-500">no in-book positions</div>}
            <div className="mt-2 text-[11px] text-slate-500">amber = above the 30% sector cap guidance</div>
          </Glass>
        </Section>
      </div>

      <Section title="Position caps in force">
        <Glass className="p-5 text-[13px] leading-7 text-slate-300">
          stop-loss never &gt; <b className="text-slate-100">10%</b> below entry · single position ≤ <b className="text-slate-100">10% of capital</b> ·
          rupee risk ≤ <b className="text-slate-100">₹10k</b> per idea (× budget multiplier) · book selected by confidence until
          <b className="text-slate-100"> ₹1.0Cr</b> fills · DD &gt; 22% halts all new cards · every rule re-derived nightly by the 98-check verify suite
        </Glass>
      </Section>
    </>
  );
}
