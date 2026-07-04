import { motion } from "framer-motion";
import { api, fmt } from "../lib/api";
import { Glass, Section, Pill, Table, useApi, TableSkeleton, ErrorState } from "../components/ui";
import { stagger } from "../lib/motion";

const VERDICT_TONE = { scored: "emerald", context: "slate", killed: "red",
                       pending_depth: "amber", passed: "emerald" };

export default function Research() {
  const v = useApi(() => api("/api/verdicts"));
  const rev = useApi(() => api("/api/review"));
  if (v.err) return <ErrorState error={v.err} retry={v.retry} />;
  if (!v.data) {
    return (
      <>
        <Section title="The verdict ledger" sub="loading…"><TableSkeleton rows={8} cols={4} /></Section>
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <TableSkeleton rows={5} cols={5} /><TableSkeleton rows={5} cols={2} />
        </div>
      </>
    );
  }
  const { preregistration, candidates, events, spine, ml_experiments, ml_paths, exit_calibration } = v.data;

  const mlBy = {};
  for (const p of ml_paths) (mlBy[p.model] = mlBy[p.model] || []).push(p.sharpe);
  const med = (a) => { const s = [...a].filter((x) => x != null).sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };

  return (
    <>
      <Section title="The verdict ledger" sub="every challenger pre-registered; nothing scores without passing its gate — 10 studies, 1 survivor">
        <Glass className="p-2">
          <Table
            cols={["Signal", "Status", "Test", "Kill / notes"]}
            rows={preregistration}
            searchKeys={[(r) => r.signal, (r) => r.status, (r) => r.test, (r) => r.notes]}
            sortAccessors={[(r) => r.signal, (r) => r.status, null, null]}
            render={(r) => [
              <span className="font-medium text-slate-200">{r.signal}</span>,
              <Pill tone={VERDICT_TONE[r.status] || "slate"}>{r.status}</Pill>,
              <span className="max-w-[380px] whitespace-normal text-[12px] text-slate-400">{r.test}</span>,
              <span className="max-w-[340px] whitespace-normal text-[12px] text-slate-500">{r.notes}</span>,
            ]}
          />
        </Glass>
      </Section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Section title="IC gate results" sub="monthly rank-IC vs forward returns · pass needs t ≥ 3 and H2 same sign">
          <Glass className="p-2">
            <Table
              cols={["Candidate", "IC", "t", "H1 → H2", "Verdict"]}
              rows={candidates}
              sortAccessors={[(r) => r.candidate, (r) => r.mean_ic, (r) => r.t_stat, null, (r) => r.verdict]}
              render={(r) => [
                r.candidate,
                <span className="num">{fmt.num(r.mean_ic, 4)}</span>,
                <span className={`num ${Math.abs(r.t_stat) >= 3 ? "text-emerald-300" : "text-slate-400"}`}>{fmt.num(r.t_stat, 2)}</span>,
                <span className="num text-slate-400">{fmt.num(r.ic_h1, 3)} → {fmt.num(r.ic_h2, 3)}</span>,
                <Pill tone={VERDICT_TONE[r.verdict]}>{r.verdict}</Pill>,
              ]}
            />
          </Glass>
        </Section>

        <Section title="ML challengers under CPCV" sub="15 purged paths · promotion needs beat-champion AND DSR>0.5 AND stability">
          <Glass className="p-4">
            {ml_experiments.map((e, i) => (
              <motion.div key={e.exp_id} {...stagger(i, { cap: 0.3 })}
                          className="mb-2 flex items-center justify-between rounded-xl border border-white/[0.06] px-4 py-3 transition-colors hover:bg-white/[0.02]">
                <div>
                  <span className="font-medium text-slate-200">{e.model_family}</span>
                  <span className="ml-2 text-[11px] text-slate-500">median path Sharpe <span className="num">{fmt.num(med(mlBy[e.model_family] || []), 2)}</span> vs champion 1.00</span>
                </div>
                <Pill tone={VERDICT_TONE[e.status] || "slate"}>{e.status}</Pill>
              </motion.div>
            ))}
            {events.map((e, i) => (
              <motion.div key={e.event_type} {...stagger(i, { cap: 0.3 })}
                          className="mb-2 flex items-center justify-between rounded-xl border border-white/[0.06] px-4 py-3 transition-colors hover:bg-white/[0.02]">
                <div>
                  <span className="font-medium text-slate-200">{e.event_type}</span>
                  <span className="ml-2 text-[11px] text-slate-500">
                    21d AR <span className="num">{fmt.pct(e.mean_ar, 2)}</span> · t <span className="num">{fmt.num(e.t_stat, 2)}</span> · n {e.n_events}
                  </span>
                </div>
                <Pill tone={VERDICT_TONE[e.verdict]}>{e.verdict}</Pill>
              </motion.div>
            ))}
            {spine.filter((s) => s.book === "IV").map((s) => (
              <div key={s.book} className="mb-2 flex items-center justify-between rounded-xl border border-white/[0.06] px-4 py-3 transition-colors hover:bg-white/[0.02]">
                <div>
                  <span className="font-medium text-slate-200">regime spine</span>
                  <span className="ml-2 text-[11px] text-slate-500">
                    OOS <span className="num">{fmt.num(s.sharpe_spine, 2)}</span> vs 4-vote <span className="num">{fmt.num(s.sharpe_incumbent, 2)}</span>
                  </span>
                </div>
                <Pill tone={s.shipped ? "emerald" : "red"}>{s.shipped ? "shipped" : "no-ship"}</Pill>
              </div>
            ))}
          </Glass>
        </Section>
      </div>

      <Section title="Exit calibration" sub="6 variants simulated on the OHLC paths of 540 closed trades · whipsaw falsified (1%)">
        <Glass className="p-2">
          <Table
            cols={["Variant", "ExpR train", "ExpR test", "Hit", "Stop rate", "MFE capture", "Verdict"]}
            rows={exit_calibration}
            render={(r) => [
              r.variant,
              <span className="num">{fmt.num(r.exp_r_train, 3)}</span>,
              <span className="num">{fmt.num(r.exp_r_test, 3)}</span>,
              <span className="num">{fmt.pct(r.hit_rate_test, 0)}</span>,
              <span className="num">{fmt.pct(r.stop_rate_test, 0)}</span>,
              <span className="num">{fmt.num(r.mfe_capture_test, 2)}</span>,
              <Pill tone={r.verdict === "KEEP" || r.verdict === "ADOPT" ? "emerald" : "slate"}>{r.verdict}</Pill>,
            ]}
          />
        </Glass>
      </Section>

      {rev.data?.latest && (
        <Section title="Latest Friday review" sub={`monitor-only · ${rev.data.latest.review_date} · proposals gated at ≥30 closed scored trades/pillar`}>
          <Glass className="p-5">
            <pre className="whitespace-pre-wrap font-sans text-[13px] leading-6 text-slate-300">
              {rev.data.latest.narrative_md?.replace(/[#*]/g, "")}
            </pre>
            {rev.data.weights?.length > 0 && (
              <div className="mt-4 border-t border-white/[0.06] pt-4">
                <div className="label mb-2">Weight versions</div>
                <WeightGrid weights={rev.data.weights} />
              </div>
            )}
          </Glass>
        </Section>
      )}
    </>
  );
}

function WeightGrid({ weights }) {
  const versions = [...new Set(weights.map((w) => w.version))];
  const pillars = [...new Set(weights.map((w) => w.pillar))];
  const get = (v, p) => weights.find((w) => w.version === v && w.pillar === p)?.weight;
  return (
    <table className="text-[12px]">
      <thead>
        <tr className="text-slate-500">
          <th className="pr-4 text-left font-medium">pillar</th>
          {versions.map((v) => <th key={v} className="num px-3 font-medium">{v}</th>)}
        </tr>
      </thead>
      <tbody>
        {pillars.map((p) => (
          <tr key={p} className="border-t border-white/[0.04]">
            <td className="pr-4 py-1 text-slate-300">{p}</td>
            {versions.map((v) => {
              const w = get(v, p);
              return <td key={v} className={`num px-3 py-1 ${w < 0 ? "text-red-300" : "text-slate-200"}`}>{w == null ? "—" : w.toFixed(2)}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
