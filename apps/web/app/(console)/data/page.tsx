import TopBar from "@/components/TopBar";
import NoRun from "@/components/Empty";
import { getLatestDataCheck, getLatestRun, getWard } from "@/lib/queries";
import { dayHour } from "@/lib/format";
import { ageWord, camsSummary, sceneDate, splitPercents } from "@/lib/datacheck";

export const dynamic = "force-dynamic";

const STATUS = { fresh: ["go", "Fresh"], stale: ["caution", "Stale, filled"], silent: ["", "Silent"] } as const;
const PARTS = [["real", "Measured"], ["filled", "Filled from CAMS"], ["synthetic", "Synthetic"]] as const;
const pct = (x: number) => `${Math.round(x * 100)}%`;

export default async function DataPage() {
  const [ward, run, chk] = await Promise.all([getWard(), getLatestRun(), getLatestDataCheck()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Data check</h1>
          <p className="lede">How much of the latest forecast rests on real, live data. Checked after every run: each source&apos;s freshness, where the last week&apos;s station hours came from, and how far the CAMS fill strays from what the stations measured.</p>
        </div>
        {!chk ? (
          <section className="panel"><div className="pb"><p className="small muted" style={{ margin: 0 }}>No data check yet. It runs after the next hourly forecast (<code>python -m dusttrace verify</code>).</p></div></section>
        ) : (
          <>
            <Summary chk={chk} stale={chk.run_id !== run.id} />
            <Stations chk={chk} />
            <Sources chk={chk} />
          </>
        )}
      </main>
    </>
  );
}

type Chk = NonNullable<Awaited<ReturnType<typeof getLatestDataCheck>>>;

function Summary({ chk, stale }: { chk: Chk; stale: boolean }) {
  const split = splitPercents(chk.shares);
  return (
    <section className="panel">
      <div className="ph">
        <h2>{chk.ok ? "Everything in this run is real, live data" : "What isn't real in this run"}</h2>
        <span className="meta">Checked {dayHour(chk.checked_at)}{stale ? " for an earlier run" : ""}</span>
      </div>
      <div className="pb">
        {split && (
          <>
            <p className="small" style={{ marginTop: 0 }}>The last week&apos;s station hours behind this forecast ({chk.shares.hours.toLocaleString("en-IN")} hours):</p>
            <div className="meter split" role="img" aria-label={PARTS.map(([k, l]) => `${l} ${split[k]}%`).join(", ")}>
              {PARTS.map(([k]) => split[k] > 0 && <span key={k} className={`seg ${k}`} style={{ width: `${split[k]}%` }} />)}
            </div>
            <p className="small muted">
              {PARTS.map(([k, label], i) => <span key={k}>{i > 0 && " · "}<span className={`key ${k}`} /> {label} <span className="tab">{split[k]}%</span></span>)}
            </p>
          </>
        )}
        {chk.problems.length > 0 && (
          <ul className="small" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {chk.problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
      </div>
    </section>
  );
}

function Stations({ chk }: { chk: Chk }) {
  const sum = camsSummary(chk.cams);
  return (
    <section className="panel">
      <div className="ph">
        <h2>Real stations</h2>
        <span className="meta">CPCB via OpenAQ · fill error from Copernicus CAMS</span>
      </div>
      <div className="pb">
        {chk.stations.length === 0 ? <p className="small muted" style={{ margin: 0 }}>No real station is loaded; the forecast runs on synthetic samples.</p> : (
          <table className="tbl">
            <thead><tr><th>Station</th><th>Newest reading</th><th>Status</th><th>CAMS fill error</th><th>Bias</th></tr></thead>
            <tbody>
              {chk.stations.map((s) => {
                const c = chk.cams[s.station_id];
                const [tone, word] = STATUS[s.status];
                return (
                  <tr key={s.station_id}>
                    <td>{s.name}</td>
                    <td>{ageWord(s.age_h)}{s.newest ? <span className="muted"> · {dayHour(s.newest)}</span> : null}</td>
                    <td><span className={`pill ${tone}`}>{word}</span></td>
                    <td className="tab">{c ? `${c.mae.toFixed(1)} µg/m³` : "–"}</td>
                    <td className="tab">{c ? `${c.bias > 0 ? "+" : ""}${c.bias.toFixed(1)} µg/m³` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <p className="small muted" style={{ marginBottom: 0 }}>
          The fill error is measured on each station&apos;s last 30 days of real readings, with the correction fitted only on the days before them, so it is the error a fill would have had.
          {sum && <> Median {sum.medianMae} µg/m³ across {sum.stations} stations; worst {chk.stations.find((s) => s.station_id === sum.worst.id)?.name ?? sum.worst.id} at {sum.worst.mae.toFixed(1)} µg/m³. A negative bias means the fill reads low.</>}
        </p>
      </div>
    </section>
  );
}

function Sources({ chk }: { chk: Chk }) {
  const s = chk.sources;
  const rows: [string, string, string, boolean][] = [
    ["Weather", "Open-Meteo forecast", `${pct(s.weather_live)} of the forecast hours live`, s.weather_live >= 1],
    ["Schools and hospitals", "OpenStreetMap", s.receptors_osm ? `${s.receptors_osm} loaded` : "Demo positions only", s.receptors_osm > 0],
    ["Homes", "Census 2011 people over OpenStreetMap residential land", s.housing_osm ? `${s.housing_osm} areas, estimated` : "Demo points only", (s.housing_osm ?? 0) > 0],
    ["Construction sites", "OpenStreetMap and confirmed satellite finds", s.sites_real ? `${s.sites_real} real sites` : "Demo sites only", s.sites_real > 0],
    ["Site discovery", "Sentinel-2", s.satellite_scene ? `Latest scene ${sceneDate(s.satellite_scene)}` : "Not run yet", !!s.satellite_scene],
  ];
  return (
    <section className="panel">
      <div className="ph"><h2>Other sources</h2><span className="meta">Run {chk.run_id}, {s.data_mode}</span></div>
      <div className="pb">
        <table className="tbl">
          <thead><tr><th>Input</th><th>Source</th><th>State</th></tr></thead>
          <tbody>
            {rows.map(([what, src, state, ok]) => (
              <tr key={what}><td>{what}</td><td className="muted">{src}</td><td><span className={`pill ${ok ? "go" : "caution"}`}>{state}</span></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
