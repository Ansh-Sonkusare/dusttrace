import TopBar from "@/components/TopBar";
import ForecastChart from "@/components/ForecastChart";
import NoRun from "@/components/Empty";
import { getForecastDays, getInputTrial, getLatestBacktest, getLatestRun, getObserved, getStationPeaks, getWard, getWardForecast } from "@/lib/queries";
import type { BtDay } from "@/lib/queries";
import { dayHour, dayShort } from "@/lib/format";
import { inputTrials, persistenceNote, stationDays, wardDays, weatherNote } from "@/lib/forecastDays";

export const dynamic = "force-dynamic";

const n = (v: number | null | undefined, d = 1) => (v == null ? "–" : v.toFixed(d));

export default async function ForecastPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [fc, obs, peaks, bt, replay, days, trial] = await Promise.all([getWardForecast(run.id), getObserved(run.issued_at, run.metrics.stations), getStationPeaks(run.id), getLatestBacktest(), getLatestBacktest("outage_replay"), getForecastDays(run.id), getInputTrial()]);
  const m = run.metrics;
  const ward3 = wardDays(days);
  const stops = weatherNote(m.weather_hours, m.forecast_hours ?? 72);
  const perStation = stationDays(days);
  const trials = inputTrials(trial?.change ?? {}, m.forecast_inputs, trial?.data_mode);
  const daily = bt?.daily;
  const beaten = persistenceNote(daily?.ward);
  const dayRow = (label: string, d: BtDay | undefined) => d && (
    <tr key={label}><td>{label}</td><td className="tab">{d.exceed_days} of {d.n}</td><td className="tab">{d.hits} / {d.misses} / {d.false_alarms}</td>
      <td className="tab">{n(d.f1_model, 2)} <span className="muted">vs {n(d.f1_persistence, 2)}</span></td><td className="tab">{n(d.brier, 3)}</td></tr>
  );

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>PM10 forecast</h1>
          <p className="lede">Ward average of the monitoring stations for the next {fc.length} hours, with the range the model expects 8 times in 10.</p>
        </div>
        <section className="panel"><div className="pb"><ForecastChart fc={fc} obs={obs} />
          {stops && <p className="small muted" style={{ margin: "8px 4px 0" }}>{stops}</p>}
        </div></section>
        <section className="panel">
          <div className="ph"><h2>Chance the 24 h mean goes above 100 µg/m³</h2><span className="meta">Ward average, the national 24 h standard for PM10</span></div>
          <div className="pb">
            {ward3.length === 0 ? <p className="small muted" style={{ margin: 0 }}>This run has no daily forecast. Runs before the 72 h forecast only gave hourly values.</p> : (
              <table className="tbl">
                <thead><tr><th>Day</th><th>Hours it covers (IST)</th><th>Chance</th></tr></thead>
                <tbody>
                  {ward3.map((d) => <tr key={d.day}><td>{d.label}</td><td>{d.hours}</td><td className="tab"><b>{d.chance}</b></td></tr>)}
                </tbody>
              </table>
            )}
            {ward3.length > 0 && ward3.length < 3 && stops && <p className="small muted" style={{ margin: "12px 0 0" }}>{stops}</p>}
          </div>
        </section>
        <div className="grid2">
          <section className="panel">
            <div className="ph"><h2>Stations</h2><span className="meta">{peaks.length} in this run</span></div>
            <div className="pb">
              <table className="tbl">
                <thead><tr><th>Station</th><th>Peak PM10</th><th>When</th><th>Hours likely above 100</th><th>Day 1</th><th>Day 2</th><th>Day 3</th></tr></thead>
                <tbody>
                  {peaks.map((p) => (
                    <tr key={p.station_id}><td>{p.name}</td><td className="tab">{Math.round(p.peak)}</td><td>{dayHour(new Date(p.peak_ts).toISOString())}</td><td className="tab">{p.hours_over}</td>
                      {(perStation.get(p.station_id) ?? ["–", "–", "–"]).map((c, k) => <td key={k} className="tab">{c}</td>)}</tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted" style={{ margin: "12px 0 0" }}>Day 1 to 3: the chance the station&apos;s 24 h mean goes above 100 µg/m³ in hours 1–24, 25–48 and 49–72 after the forecast was issued.</p>
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
            {daily?.ward && (
              <div className="pb">
                <table className="tbl">
                  <thead><tr><th>24 h mean above 100</th><th>Measured above 100</th><th>Caught / missed / false alarms</th><th>F1, model vs persistence</th><th>Brier score</th></tr></thead>
                  <tbody>
                    {[1, 2, 3].map((d) => dayRow(`Ward, day ${d}`, daily.ward?.[String(d)]))}
                    {[1, 2, 3].map((d) => dayRow(`Stations, day ${d}`, daily.stations?.[String(d)]))}
                  </tbody>
                </table>
                {daily.window && <p className="small" style={{ margin: "12px 0 0" }}>The window held <b>{daily.window.ward_exceed_days} of {daily.window.ward_days} days</b> with the ward&apos;s measured 24 h mean above 100 µg/m³, and {daily.window.station_exceed_days} of {daily.window.station_days} station-days. Each measured day counts once, though days 1 to 3 of successive forecasts score it up to three times.</p>}
                {beaten && <p className="small" style={{ margin: "8px 0 0" }}><b>{beaten}</b></p>}
                <p className="small muted" style={{ margin: "8px 0 0" }}>
                  A day is the 24 hours after the issue time, needs 18 measured hours, and counts as called when the chance is 50% or more. Persistence calls a day above 100 when the 24 h before the issue time were.
                  Lower Brier scores are better.
                </p>
              </div>
            )}
          </section>
        )}
        <section className="panel">
          <div className="ph">
            <h2>New inputs on trial</h2>
            <span className="meta">{trial ? <>{trial.origins} daily forecasts, {dayShort(trial.train_end)} to {dayShort(trial.test_end)}{trial.data_mode !== "live" && <> · <span className="pill dust">{trial.data_mode === "synthetic" ? "Synthetic" : "Partly synthetic weather"}</span></>}</> : "Not tried yet"}</span>
          </div>
          <div className="pb">
            <table className="tbl">
              <thead><tr><th>Input</th><th>Change in error</th><th>Change in F1, hours above 100</th><th>Change in F1, days above 100</th><th>In runs</th></tr></thead>
              <tbody>
                {trials.map((t) => (
                  <tr key={t.name}><td>{t.name}</td><td className="tab">{t.mae}</td><td className="tab">{t.f1Hourly}</td><td className="tab">{t.f1Daily}</td>
                    <td>{t.inRuns ? <b>{t.verdict}</b> : t.verdict}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="small muted" style={{ margin: "12px 0 0" }}>
              The festival calendar marks Diwali, Ganeshotsav, Holi, Dasara and New Year. Construction sites upwind counts the hectares of real mapped sites within 3 km in the direction the wind blows from;
              sites outside the pilot wards are missing.
              {trial ? ` ${trial.note ?? ""}` : " Each input is back-tested on the same window with and without it, and stays on only if the error does not rise and neither F1 falls. The site list has no dates, so on past days it uses today's sites. Run python -m dusttrace backtest --compare-inputs to try them; until then both stay off."}
            </p>
          </div>
        </section>
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
