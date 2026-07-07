import { api, fmt } from "../lib/api";
import { Glass, Section, Stat, Pill, Table, useApi, StatSkeleton, TableSkeleton, ErrorState } from "../components/ui";

const TONE_TYPE = { momentum: "cyan", event: "violet" };
const TONE_REASON = { target: "emerald", stop: "red", expired: "slate" };

function daysAgo(dateStr) {
  if (!dateStr) return null;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
}

export default function Portfolio() {
  const pf = useApi(() => api("/api/portfolio"));
  if (pf.err) return <ErrorState error={pf.err} retry={pf.retry} />;
  if (!pf.data) {
    return (
      <>
        <StatSkeleton n={5} />
        <div className="mt-8"><TableSkeleton rows={8} cols={7} /></div>
      </>
    );
  }
  const { summary, open, closed } = pf.data;

  // "price_as_of" is the latest close on file per symbol -- these positions'
  // mark-to-market is only as fresh as that, which is a separate table from
  // the daily price feed and can lag it. Surface the staleness rather than
  // silently imply the P&L below is live.
  const priceAges = open.map((p) => daysAgo(p.price_as_of)).filter((d) => d != null);
  const maxAge = priceAges.length ? Math.max(...priceAges) : null;
  const stale = maxAge != null && maxAge > 3;

  return (
    <>
      <Section
        title="Portfolio"
        sub={`${summary.open_count} open · ${summary.closed_count} closed`}
        right={
          maxAge != null && (
            <Pill tone={stale ? "amber" : "emerald"}>
              mark-to-market prices {maxAge === 0 ? "today" : `${maxAge}d old`}
            </Pill>
          )
        }
      >
        <div className="flex flex-wrap gap-4">
          <Stat label="Open positions" value={summary.open_count} format={(v) => v.toFixed(0)}
                sub={summary.open_unsized_count ? `${summary.open_unsized_count} unsized, excluded from ₹ totals` : undefined} />
          <Stat label="Deployed" value={summary.deployed} format={(v) => "₹" + (v / 1e5).toFixed(1) + "L"} accent="text-cyan-300" />
          <Stat label="Unrealized P&L" value={summary.unrealized_total} format={(v) => (v >= 0 ? "+" : "") + "₹" + (v / 1e5).toFixed(2) + "L"}
                accent={summary.unrealized_total >= 0 ? "text-emerald-300" : "text-red-300"} />
          <Stat label="Closed trades" value={summary.closed_count} format={(v) => v.toFixed(0)} />
          <Stat label="Win rate" value={summary.win_rate} format={fmt.pct} />
          <Stat label="Avg realized return" value={summary.avg_realized_return} format={fmt.pct}
                accent={summary.avg_realized_return >= 0 ? "text-emerald-300" : "text-red-300"} />
        </div>
      </Section>

      <Section title="Open positions" sub="entry vs. current close on file · unrealized P&L only computable where size is on record">
        <Glass className="p-2">
          <Table
            cols={["Symbol", "Type", "Entry", "Current", "Unrealized", "Stop", "Target", "Notional"]}
            rows={open}
            searchKeys={[(r) => r.symbol]}
            sortAccessors={[(r) => r.symbol, (r) => r.thesis_type, (r) => r.entry_date,
                            (r) => r.current_price, (r) => r.unrealized_pct, (r) => r.stop,
                            (r) => r.target, (r) => r.notional]}
            render={(r) => [
              <span className="font-medium text-slate-200">{r.symbol}</span>,
              <Pill tone={TONE_TYPE[r.thesis_type] || "slate"}>{r.thesis_type}</Pill>,
              <span className="num text-slate-400">{fmt.inr(r.entry_price)}<span className="ml-1 text-[10px] text-slate-600">{r.entry_date}</span></span>,
              <span className="num">{r.current_price != null ? fmt.inr(r.current_price) : "—"}</span>,
              r.unrealized_pct != null
                ? <span className={`num ${r.unrealized_pct >= 0 ? "text-emerald-300" : "text-red-300"}`}>{fmt.pct(r.unrealized_pct)}</span>
                : <span className="text-slate-600">—</span>,
              <span className="num text-red-300/80">{fmt.inr(r.stop)}</span>,
              <span className="num text-emerald-300/80">{fmt.inr(r.target)}</span>,
              <span className="num text-slate-400">{r.notional != null ? fmt.inr(r.notional) : "—"}</span>,
            ]}
          />
        </Glass>
      </Section>

      <Section title="Closed trades" sub={`${closed.length} settled · realized return is a %, not currency (size wasn't tracked on the oldest closed trades)`}>
        <Glass className="p-2">
          <Table
            animateRows={false}
            cols={["Symbol", "Type", "Entry", "Exit", "Reason", "Return"]}
            rows={closed}
            searchKeys={[(r) => r.symbol, (r) => r.exit_reason]}
            sortAccessors={[(r) => r.symbol, (r) => r.thesis_type, (r) => r.entry_date,
                            (r) => r.exit_date, (r) => r.exit_reason, (r) => r.realized_return]}
            render={(r) => [
              <span className="font-medium text-slate-200">{r.symbol}</span>,
              <Pill tone={TONE_TYPE[r.thesis_type] || "slate"}>{r.thesis_type}</Pill>,
              <span className="num text-slate-500">{r.entry_date}</span>,
              <span className="num text-slate-400">{r.exit_date}</span>,
              <Pill tone={TONE_REASON[r.exit_reason] || "slate"}>{r.exit_reason || "—"}</Pill>,
              <span className={`num ${r.realized_return >= 0 ? "text-emerald-300" : "text-red-300"}`}>{fmt.pct(r.realized_return)}</span>,
            ]}
          />
        </Glass>
      </Section>
    </>
  );
}
