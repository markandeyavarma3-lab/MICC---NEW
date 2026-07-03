import { api, fmt } from "../lib/api";
import { Glass, Section, Table, Loading, useApi } from "../components/ui";

export default function Funds() {
  const funds = useApi(() => api("/api/funds"));
  if (!funds.data) return <Loading />;
  return (
    <Section title="Equity funds" sub="direct-growth plans ranked by 3-year Sharpe · from the 847-fund scorecard">
      <Glass className="p-2">
        <Table
          cols={["Fund", "AMC", "Category", "3y CAGR", "3y Sharpe", "Max DD"]}
          rows={funds.data}
          render={(r) => [
            <span className="max-w-[320px] truncate font-medium text-slate-200">{r.scheme_name}</span>,
            <span className="text-slate-400">{(r.amc || "").replace(" Mutual Fund", "")}</span>,
            r.cat_short,
            <span className="num">{fmt.pct(r.cagr_3y, 1)}</span>,
            <span className="num text-cyan-300">{fmt.num(r.sharpe_3y, 2)}</span>,
            <span className="num text-red-300">{fmt.pct(r.max_dd, 0)}</span>,
          ]}
        />
      </Glass>
    </Section>
  );
}
