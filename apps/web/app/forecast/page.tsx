import TopBar from "@/components/TopBar";
import ForecastChart from "@/components/ForecastChart";
import NoRun from "@/components/Empty";
import { getLatestRun, getObserved, getStationPeaks, getWard, getWardForecast } from "@/lib/queries";
import { dayHour } from "@/lib/format";

export const dynamic = "force-dynamic";

const n = (v: number | undefined, d = 1) => (v === undefined ? "–" : v.toFixed(d));

export default async function ForecastPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [fc, obs, peaks] = await Promise.all([getWardForecast(run.id), getObserved(run.issued_at, run.metrics.stations), getStationPeaks(run.id)]);
  const m = run.metrics;

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>PM10 forecast</h1>
          <p className="lede">Ward average of the monitoring stations, with the range the model expects 8 times in 10.</p>
        </div>
        <section className="panel"><div className="pb"><ForecastChart fc={fc} obs={obs} /></div></section>
        <div className="grid2">
          <section className="panel">
            <div className="ph"><h2>Stations</h2><span className="meta">{peaks.length} in this run</span></div>
            <div className="pb">
              <table className="tbl">
                <thead><tr><th>Station</th><th>Peak PM10</th><th>When</th><th>Hours likely above 100</th></tr></thead>
                <tbody>
                  {peaks.map((p) => (
                    <tr key={p.station_id}><td>{p.name}</td><td className="tab">{Math.round(p.peak)}</td><td>{dayHour(new Date(p.peak_ts).toISOString())}</td><td className="tab">{p.hours_over}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <div className="ph"><h2>How good is it</h2><span className="meta">{run.model}</span></div>
            <div className="pb">
              <table className="tbl">
                <thead><tr><th>Held-out test</th><th>Model</th><th>Persistence</th></tr></thead>
                <tbody>
                  <tr><td>Mean error, µg/m³</td><td className="tab">{n(m.mae_model)}</td><td className="tab">{n(m.mae_persistence)}</td></tr>
                  <tr><td>F1 for hours above 100</td><td className="tab">{n(m.f1_exceed_model, 2)}</td><td className="tab">{n(m.f1_exceed_persistence, 2)}</td></tr>
                  <tr><td>Inside likely range</td><td className="tab">{m.coverage_10_90 !== undefined ? `${Math.round(m.coverage_10_90 * 100)}%` : "–"}</td><td className="muted">target 80%</td></tr>
                </tbody>
              </table>
              <p className="small muted" style={{ marginTop: 12 }}>Persistence assumes the next hours look like the last one. The test set is the latest 20% of history, never seen in training.</p>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
