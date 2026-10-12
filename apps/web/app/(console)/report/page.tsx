import TopBar from "@/components/TopBar";
import NoRun from "@/components/Empty";
import { getLatestRun, getWard, getWeeklyData } from "@/lib/queries";
import { ACTION_LABEL } from "@/lib/format";
import { OUTCOMES } from "@/lib/officer";
import { countBy, spikeDays, type DayResult } from "@/lib/weekly";
import { siteLabel } from "@/lib/sites";

export const dynamic = "force-dynamic";

const RESULT: Record<DayResult, [string, string]> = {
  hit: ["go", "Forecast and seen"], missed: ["avoid", "Missed"], false_alarm: ["caution", "False alarm"],
  quiet: ["", "Quiet, as forecast"], no_data: ["", "No measured data"],
};
const VERDICT: Record<string, string> = { drop: "dropped", no_drop: "no drop", insufficient: "not enough data" };
const dayName = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

export default async function WeeklyReport() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const w = await getWeeklyData();
  const days = spikeDays(w.forecast, w.observed);
  const rules = countBy(w.actions, "rule");
  const acts = countBy(w.actions, "action");
  const outcomes = countBy(w.inspections, "outcome");
  const checks = countBy(w.checks, "verdict");
  const bands = countBy(w.scores, "band");
  const total = w.real_hours + w.filled_or_synthetic_hours;

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view report">
        <div>
          <h1>Weekly ward report</h1>
          <p className="lede">{ward.name}, the 7 days to {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Kolkata" })}. Each number names its source. Print this page or save it as PDF from the browser.</p>
          {total > 0 && <p className="small muted">Station data this week: {Math.round((w.real_hours / total) * 100)}% measured station hours (CPCB via OpenAQ); the rest synthetic samples. Hours filled from Copernicus CAMS are not readings and are not counted here.</p>}
        </div>

        <section className="panel">
          <div className="ph"><h2>Spike days: forecast against what the stations measured</h2><span className="meta">Forecast issued 12 h or more ahead · ward mean of measured hours</span></div>
          <div className="pb">
            {days.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No forecasts or readings this week.</p> : (
              <table className="tbl">
                <thead><tr><th>Day (IST)</th><th>Forecast P(PM10 &gt; 100) ≥ 0.6</th><th>Ward mean above 100 µg/m³</th><th>Result</th></tr></thead>
                <tbody>{days.map((d) => (
                  <tr key={d.day}><td>{dayName(d.day)}</td><td>{d.forecast ? "Yes" : "No"}</td><td>{d.result === "no_data" ? "–" : d.observed ? "Yes" : "No"}</td>
                    <td><span className={`pill ${RESULT[d.result][0]}`}>{RESULT[d.result][1]}</span></td></tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="ph"><h2>What the agent did</h2><span className="meta">Case actions this week, by rule · cases table</span></div>
          <div className="pb grid-case">
            <table className="tbl"><thead><tr><th>Rule</th><th>Actions</th></tr></thead>
              <tbody>{rules.length ? rules.map(([r, n]) => <tr key={r}><td>{r}</td><td className="tab">{n}</td></tr>) : <tr><td colSpan={2} className="muted">None</td></tr>}</tbody></table>
            <table className="tbl"><thead><tr><th>Action</th><th>Count</th></tr></thead>
              <tbody>{acts.slice(0, 8).map(([a, n]) => <tr key={a}><td>{ACTION_LABEL[a] ?? a}</td><td className="tab">{n}</td></tr>)}</tbody></table>
          </div>
        </section>

        <section className="panel">
          <div className="ph"><h2>Inspections and checks</h2><span className="meta">Officer outcomes · verifications table</span></div>
          <div className="pb grid-case">
            <table className="tbl"><thead><tr><th>Inspection outcome</th><th>Visits</th></tr></thead>
              <tbody>{outcomes.length ? outcomes.map(([o, n]) => <tr key={o}><td>{OUTCOMES[o as keyof typeof OUTCOMES] ?? o}</td><td className="tab">{n}</td></tr>) : <tr><td colSpan={2} className="muted">No inspections logged</td></tr>}</tbody></table>
            <table className="tbl"><thead><tr><th>Did PM10 fall after a fix?</th><th>Checks</th></tr></thead>
              <tbody>{checks.length ? checks.map(([v, n]) => <tr key={v}><td>{VERDICT[v] ?? v}</td><td className="tab">{n}</td></tr>) : <tr><td colSpan={2} className="muted">None checked yet</td></tr>}</tbody></table>
          </div>
        </section>

        <section className="panel">
          <div className="ph"><h2>Dust Scores</h2><span className="meta">Latest run · {bands.map(([b, n]) => `${n} ${b}`).join(", ")}</span></div>
          <div className="pb">
            <table className="tbl"><thead><tr><th>Lowest scores</th><th>Score</th><th>Band</th></tr></thead>
              <tbody>{w.scores.slice(0, 8).map((s) => (
                <tr key={s.site_id}><td>{siteLabel(s.site_id, s.name)}{s.demo ? " (demo)" : ""}</td><td className="tab">{Math.round(s.score)}</td><td>{s.band}</td></tr>
              ))}</tbody></table>
          </div>
        </section>
        <p className="small muted">Team ARA IGNITE: Ansh, Dhruv, Anuj, Sarang. Data: CPCB via OpenAQ, Copernicus CAMS and Open-Meteo, OpenStreetMap contributors (ohsome), Census of India 2011, Copernicus Sentinel-2.</p>
      </main>
    </>
  );
}
