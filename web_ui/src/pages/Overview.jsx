import { useMemo } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api, C, fmt } from "../lib/api";
import { Glass, Section, Stat, Badge, Pill, Loading, useApi, tooltipStyle, CountUp } from "../components/ui";

export default function Overview() {
  const regime = useApi(() => api("/api/regime"));
  const risk = useApi(() => api("/api/risk"));
  const best = useApi(() => api("/api/best"));
  const ideas = useApi(() => api("/api/ideas"));
  const strat = useApi(() => api("/api/strategies"));
  const health = useApi(() => api("/api/health"));

  const bestM = useMemo(() => {
    const s = strat.data;
    if (!s) return null;
    return s.find((x) => x.strategy === "LO + Regime gate") || s[0];
  }, [strat.data]);

  const series = useMemo(
    () => (best.data ? best.data.series.filter((_, i) => i % 1 === 0) : []),
    [best.data]
  );

  if (!regime.data || !risk.data) return <Loading />;

  const r = regime.data;
  const riskOn = r.pct_above_200dma >= 50; // display only; votes below are the gate
  const rc = risk.data.current || {};
  const votes = rc.regime_votes ?? null;
  const gateOn = votes != null ? votes >= 2 : riskOn;
  const book = ideas.data;
  const deployed = book ? book.cards.filter((c) => c.in_book !== 0).reduce((a, c) => a + (c.entry * c.size_shares || 0), 0) : null;

  return (
    <>
      {/* ===== HERO: regime + risk state ===== */}
      <div className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Glass className={`relative overflow-hidden p-6 lg:col-span-2 ${gateOn ? "" : ""}`}>
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background: gateOn
                ? "radial-gradient(600px 200px at 20% 0%, rgba(16,185,129,.18), transparent 60%)"
                : "radial-gradient(600px 200px at 20% 0%, rgba(239,68,68,.15), transparent 60%)",
            }}
          />
          <div className="relative">
            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Market regime · 4-vote gate</div>
            <div className="mt-2 flex items-center gap-4">
              <span className={`text-4xl font-bold tracking-tight ${gateOn ? "text-emerald-300" : "text-red-300"}`}>
                {gateOn ? "RISK-ON" : "RISK-OFF"}
              </span>
              <span className="num text-xl text-slate-400">{votes ?? "—"}/4</span>
              <Badge ok={gateOn} pulse>{gateOn ? "book held" : "gate to cash bias"}</Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Pill tone={r.pct_above_200dma >= 50 ? "emerald" : "red"}>breadth {fmt.num(r.pct_above_200dma, 0)}% &gt;200DMA</Pill>
              <Pill tone="slate">as of {r.date}</Pill>
              {rc.notes && <Pill tone="slate">{rc.notes.split(";")[0]}</Pill>}
            </div>
          </div>
        </Glass>

        <Glass className="p-6">
          <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Risk meta-engine</div>
          <div className="mt-3 space-y-2.5 text-[13px]">
            <Row k="Drawdown" v={fmt.pct(rc.drawdown_pct)} warn={rc.drawdown_pct >= 0.10} />
            <Row k="Budget multiplier" v={`×${rc.risk_budget_mult ?? "—"}`} warn={rc.risk_budget_mult < 1} />
            <Row k="Loss streak" v={rc.consec_losses ?? "—"} warn={rc.consec_losses >= 3} />
            <Row k="Holdings corr (60d)" v={fmt.num(rc.avg_pairwise_corr)} warn={rc.avg_pairwise_corr > 0.6} />
            <Row k="New cards" v={rc.halt_new_cards ? "HALTED" : "allowed"} warn={!!rc.halt_new_cards} />
          </div>
        </Glass>
      </div>

      {/* ===== headline stats ===== */}
      <Section title="Flagship — inverse-vol + walk-forward regime gate" sub="out-of-sample 2009→2026, net of costs">
        <div className="flex flex-wrap gap-4">
          <Stat label="Sharpe (OOS)" value={bestM?.Sharpe} accent="text-cyan-300" />
          <Stat label="CAGR" value={bestM?.CAGR} format={(v) => (v * 100).toFixed(1) + "%"} />
          <Stat label="Max drawdown" value={bestM?.MaxDD} format={(v) => (v * 100).toFixed(0) + "%"} accent="text-red-300" />
          <Stat label="Calmar" value={bestM?.Calmar} />
          <Stat label="Desk R-PnL" value={rc.equity} format={(v) => "₹" + (v / 1e5).toFixed(1) + "L"} accent="text-emerald-300" sub="540+ closed trades" />
          <Stat label="Green streak" value={health.data ? `${health.data.streak}/${health.data.target}` : "—"} sub="unattended runs gate" />
        </div>
      </Section>

      {/* ===== equity curve ===== */}
      <Section title="Equity curve" sub="growth of ₹1 — log scale · hover for detail">
        <Glass className="p-4">
          {best.data ? (
            <ResponsiveContainer width="100%" height={340}>
              <AreaChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.cyan} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={C.cyan} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" minTickGap={70} tickLine={false} axisLine={false} />
                <YAxis scale="log" domain={["auto", "auto"]} tickFormatter={(v) => v.toFixed(0) + "x"} tickLine={false} axisLine={false} width={44} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v, name) => (name === "equity" ? [Number(v).toFixed(2) + "x", "equity"] : [fmt.pct(v), "drawdown"])}
                />
                <Area type="monotone" dataKey="equity" stroke={C.cyan} strokeWidth={2} fill="url(#eq)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Loading />}
        </Glass>
      </Section>

      {/* ===== book snapshot ===== */}
      <Section title="Live book" sub={book ? `${book.n} cards · ${book.card_date}` : ""}>
        <div className="flex flex-wrap gap-4">
          <Stat label="Deployed" value={deployed} format={(v) => "₹" + (v / 1e5).toFixed(1) + "L"} sub="of ₹1.0Cr capital" accent="text-cyan-300" />
          <Stat label="In book" value={book ? book.cards.filter((c) => c.in_book !== 0).length : null} format={(v) => v.toFixed(0)} />
          <Stat label="Top idea" value={book?.cards[0]?.symbol} sub={book ? `conf ${fmt.num(book.cards[0]?.confidence_score, 0)}` : ""} />
          <Stat label="Avg confidence" value={book ? book.cards.reduce((a, c) => a + c.confidence_score, 0) / book.n : null} format={(v) => v.toFixed(1)} />
        </div>
      </Section>
    </>
  );
}

function Row({ k, v, warn }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.05] pb-2">
      <span className="text-slate-400">{k}</span>
      <span className={`num font-medium ${warn ? "text-amber-300" : "text-slate-200"}`}>{v}</span>
    </div>
  );
}
