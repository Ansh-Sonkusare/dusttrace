import TopBar from "@/components/TopBar";
import ForecastChart from "@/components/ForecastChart";
import NoRun from "@/components/Empty";
import { getLatestBacktest, getLatestRun, getObserved, getStationPeaks, getWard, getWardForecast } from "@/lib/queries";
import { dayHour, dayShort } from "@/lib/format";

export const dynamic = "force-dynamic";

const n = (v: number | undefined, d = 1) => (v === undefined ? "–" : v.toFixed(d));

export default async function ForecastPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [fc, obs, peaks, bt, replay] = await Promise.all([getWardForecast(run.id), getObserved(run.issued_at, run.metrics.stations), getStationPeaks(run.id), getLatestBacktest(), getLatestBacktest("outage_replay")]);
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
        {bt && (
          <section className="panel">
            <div className="ph">
              <h2>Back-test on {bt.data_mode === "synthetic" ? "synthetic" : "real CPCB"} data</h2>
              <span className="meta">{bt.stations.length} stations · {bt.origins} daily forecasts, {dayShort(bt.train_end)} to {dayShort(bt.test_end)}{bt.data_mode !== "live" && <> · <span className="pill dust">{bt.data_mode === "synthetic" ? "Synthetic" : "Partly synthetic weather"}</span></>}</span>
            </div>
            <div className="pb grid-case">
              <table className="tbl">
                <thead><tr><th>Hours ahead</th><th>Model error</th><th>Persistence error</th><th>F1 above 100</th><th>Inside likely range</th></tr></thead>
                <tbody>
                  {Object.entries(bt.metrics).map(([k, b]) => (
                    <tr key={k}><td>{k}</td><td className="tab">{n(b.mae_model)} µg/m³</td><td className="tab">{n(b.mae_persistence)} µg/m³</td>
                      <td className="tab">{n(b.f1_exceed_model, 2)} <span className="muted">vs {n(b.f1_exceed_persistence, 2)}</span></td>
                      <td className="tab">{Math.round(b.coverage_10_90 * 100)}%</td></tr>
                  ))}
                </tbody>
              </table>
              <div className="small">
                {bt.spike_day && (
                  <>
                    <p style={{ margin: "0 0 6px" }}><b>Worst day: {dayShort(`${bt.spike_day.day}T12:00:00+05:30`)}</b></p>
                    <p className="muted" style={{ margin: "0 0 12px" }}>
                      Ward average {Math.round(bt.spike_day.actual_mean)} µg/m³.
                      {bt.spike_day.lead_hours != null && bt.spike_day.p_exceed_max != null
                        ? ` The forecast issued ${bt.spike_day.lead_hours} hours earlier gave a ${Math.round(bt.spike_day.p_exceed_max * 100)}% chance of going above 100${bt.spike_day.flagged ? ", so it was flagged." : ", below the 50% flag."}`
                        : " No forecast was issued early enough to judge."}
                    </p>
                  </>
                )}
                <p className="muted" style={{ margin: 0 }}>Each forecast saw only data up to its issue time; the model was trained on earlier months. {bt.note}</p>
              </div>
            </div>
          </section>
        )}
        {replay && (
          <section className="panel">
            <div className="ph">
              <h2>When the station feed is down</h2>
              <span className="meta">{replay.origins} forecasts, {dayShort(replay.train_end)} to {dayShort(replay.test_end)}, real CPCB data</span>
            </div>
            <div className="pb grid-case">
              <table className="tbl">
                <thead><tr><th>Forecast made with</th><th>Error, next 24 h</th><th>Error, 25–48 h</th></tr></thead>
                <tbody>
                  {([["real", "Real readings (no outage)"], ["filled", "Last 4 days filled from corrected CAMS"], ["cams_direct", "Corrected CAMS on its own"], ["last_value", "Last real value carried forward"]] as const).map(([k, label]) => {
                    const m = (replay.metrics as unknown as Record<string, Record<string, { mae_model: number }>>)[k];
                    return m ? <tr key={k}><td>{label}</td><td className="tab">{n(m["1-24"]?.mae_model)} µg/m³</td><td className="tab">{n(m["25-48"]?.mae_model)} µg/m³</td></tr> : null;
                  })}
                </tbody>
              </table>
              <p className="small muted" style={{ margin: 0 }}>We hid the last 4 days of every station before each forecast and filled them from Copernicus CAMS, corrected against each station&apos;s own history, then compared the forecast with what the stations measured. This is how much the fill costs when the CPCB feed stops. {replay.note}</p>
            </div>
          </section>
        )}
      </main>
    </>
  );
}
