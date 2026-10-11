import TopBar from "@/components/TopBar";
import DustMap from "@/components/DustMap";
import NoRun from "@/components/Empty";
import Link from "next/link";
import { getLatestRun, getPlumes, getReceptors, getSites, getStations, getWard, getWardForecast, getWeather, getWindows } from "@/lib/queries";
import { buildMapHours, spans } from "@/lib/mapHours";
import { dayHour, hhmm } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);

  const [fc, windows, plumes, wx, sites, receptors, stations] = await Promise.all([
    getWardForecast(run.id), getWindows(run.id), getPlumes(run.id), getWeather(run.issued_at),
    getSites(), getReceptors(), getStations(run.metrics.stations),
  ]);
  const hours = buildMapHours(windows, plumes, wx);
  const peak = fc.length ? fc.reduce((a, b) => (b.pm10 > a.pm10 ? b : a)) : null;
  const likelyOver = fc.filter((f) => f.p_exceed >= 0.5).length;
  const cut24 = new Date(run.issued_at).getTime() + 24 * 3600_000;
  const avoid24 = windows.filter((w) => w.status === "avoid" && new Date(w.ts).getTime() <= cut24).length;
  const firstTs = hours[0]?.ts;
  const exposedNow = windows.filter((w) => w.ts === firstTs).reduce((s, w) => s + w.exposed_people, 0);

  const nextAvoid = sites.flatMap((s) =>
    spans(windows.filter((w) => w.site_id === s.id)).filter((sp) => sp.status === "avoid").slice(0, 1).map((sp) => ({ site: s, sp })),
  ).sort((a, b) => a.sp.from.localeCompare(b.sp.from));

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Next 48 hours in {ward.name}</h1>
          <p className="lede">Where construction dust will travel, who it reaches, and when each site should hold dusty work.</p>
        </div>
        {run.data_mode !== "live" && (
          <div className="banner">This run uses {run.data_mode === "mixed" ? "partly " : ""}synthetic readings or weather because the live sources were unreachable. Treat the numbers as a demonstration until the live ingest runs.</div>
        )}
        <section className="stats" aria-label="Summary">
          <div className="panel stat"><span className="v">{peak ? Math.round(peak.pm10) : "–"}</span><span className="d">Peak ward PM10, µg/m³<br />{peak ? dayHour(peak.ts) : ""}</span></div>
          <div className="panel stat"><span className="v">{likelyOver}</span><span className="d">Hours likely above<br />the 100 standard</span></div>
          <div className="panel stat"><span className="v">{avoid24}</span><span className="d">Site-hours to avoid<br />in the next 24 h</span></div>
          <div className="panel stat"><span className="v">{exposedNow.toLocaleString("en-IN")}</span><span className="d">People inside a plume<br />this hour</span></div>
        </section>
        <div className="grid2">
          <section className="panel" aria-label="Plume map">
            <div className="ph"><h2>Plume map</h2><span className="meta">Gaussian plume, hourly</span></div>
            <DustMap center={[ward.center_lon, ward.center_lat]} sites={sites} receptors={receptors} stations={stations} hours={hours} />
          </section>
          <section className="panel" aria-label="Next hold periods">
            <div className="ph"><h2>Next hold periods</h2><Link className="meta" href="/sites">All sites</Link></div>
            <div className="pb">
              {nextAvoid.length === 0 ? <p className="small muted">No site needs to hold dusty work in this forecast.</p> : (
                <ul className="list">
                  {nextAvoid.map(({ site, sp }) => (
                    <li key={site.id}>
                      <Link href={`/sites/${site.id}`} className="item">
                        <span className="bar" style={{ background: "var(--avoid)" }} />
                        <div>
                          <div className="hd"><b>{site.id} · {site.name}</b></div>
                          <div className="small" style={{ marginTop: 2 }}>Avoid {dayHour(sp.from)}–{hhmm(new Date(new Date(sp.to).getTime() + 3600_000).toISOString())}</div>
                          <p>{sp.rows[0].reason}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
