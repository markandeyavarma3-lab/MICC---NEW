import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api, C, fmt } from "../lib/api";
import { Glass, Section, Pill, Table, useApi, tooltipStyle, TableSkeleton, ChartSkeleton, ErrorState } from "../components/ui";
import { useSymbol } from "../lib/symbolContext";

const TIER_TONE = { scored: "emerald", context: "slate", risk: "red" };

export default function Events() {
  const ev = useApi(() => api("/api/events"));
  const { open: openSymbol } = useSymbol();
  if (ev.err) return <ErrorState error={ev.err} retry={ev.retry} />;
  if (!ev.data) {
    return (
      <>
        <Section title="Event shadow scoreboard" sub="loading…"><TableSkeleton rows={6} cols={6} /></Section>
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <TableSkeleton rows={6} cols={4} /><ChartSkeleton height={200} />
        </div>
      </>
    );
  }
  const { recent, shadow, tags } = ev.data;
  const tagData = tags.filter((t) => t.tag !== "other" && t.tag !== "meeting_admin").slice(0, 10);

  return (
    <>
      <Section title="Event shadow scoreboard" sub="would-be event ideas, forward returns at 63td · promotion needs ≥12mo AND ≥30 filled AND beats the 49% baseline">
        <Glass className="p-2">
          <Table
            cols={["Event type", "Instances", "Filled 63d", "Hit rate", "Avg 63d", "Gate"]}
            rows={shadow}
            render={(r) => [
              <span className="font-medium text-slate-200">{r.event_type}</span>,
              <span className="num">{r.n}</span>,
              <span className="num">{r.filled63 ?? 0}</span>,
              <span className="num">{r.hit63 == null ? "—" : fmt.pct(r.hit63, 0)}</span>,
              <span className={`num ${r.avg63 > 0 ? "text-emerald-300" : "text-red-300"}`}>{r.avg63 == null ? "—" : fmt.pct(r.avg63, 1)}</span>,
              (r.filled63 ?? 0) >= 30
                ? <Pill tone="cyan">sample OK · time-gated to ~2027</Pill>
                : <Pill tone="amber">needs ≥30 filled</Pill>,
            ]}
          />
        </Glass>
      </Section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Section title="Recent events" sub="evidence-tiered — only 'scored' carries weight">
          <Glass className="max-h-[460px] overflow-y-auto p-2">
            <Table
              cols={["Date", "Symbol", "Type", "Tier"]}
              rows={recent}
              searchKeys={[(r) => r.symbol, (r) => r.event_type]}
              sortAccessors={[(r) => r.event_date, (r) => r.symbol, (r) => r.event_type, (r) => r.evidence_tier]}
              render={(r) => [
                <span className="num text-slate-400">{r.event_date}</span>,
                <button onClick={() => openSymbol(r.symbol)}
                        className="font-medium text-slate-200 underline decoration-white/20 underline-offset-2 transition-colors hover:text-cyan-300 hover:decoration-cyan-300/50">
                  {r.symbol}
                </button>,
                r.event_type,
                <Pill tone={TIER_TONE[r.evidence_tier] || "slate"}>{r.evidence_tier}</Pill>,
              ]}
            />
          </Glass>
        </Section>

        <Section title="Announcement taxonomy" sub="16,963 announcements auto-classified (admin/other hidden)">
          <Glass className="p-4">
            <ResponsiveContainer width="100%" height={tagData.length * 34 + 16}>
              <BarChart data={tagData} layout="vertical" margin={{ top: 4, right: 52, bottom: 0, left: 8 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="tag" width={130} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => [v.toLocaleString(), "count"]} />
                <Bar dataKey="n" fill={C.violet} radius={[4, 4, 4, 4]} barSize={16}
                     animationDuration={700} animationEasing="ease-out"
                     label={{ position: "right", fill: "#94a3b8", fontSize: 11 }} />
              </BarChart>
            </ResponsiveContainer>
          </Glass>
        </Section>
      </div>
    </>
  );
}
