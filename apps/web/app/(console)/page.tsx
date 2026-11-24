import TopBar from "@/components/TopBar";
import { siteLabel } from "@/lib/sites";
import DustMap from "@/components/DustMap";
import NoRun from "@/components/Empty";
import Link from "next/link";
import { getAcceptedAvoided, getAlerts, getKpis, getLatestRun, getPlumes, getReceptors, getSites, getNodes, getStations, getWard, getWardExposure, getWardForecast, getWeather, getWindows } from "@/lib/queries";
import { EXPOSURE_DEFINITION, fmtExposure, moveText } from "@/lib/exposure";
import { kpiTiles } from "@/lib/kpi";
import { dataNotice } from "@/lib/notice";
import { buildMapHours, spans } from "@/lib/mapHours";
import { spanText } from "@/lib/format";

export const dynamic = "force-dynamic";

const ALERT_TONE = { critical: "var(--avoid)", action: "var(--caution)", receptor: "var(--dust)", sensor: "var(--line-2)" } as const;

export default async function Overview() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);

  const [fc, windows, plumes, wx, sites, receptors, stations, kpis, alerts, nodes, ex, accepted] = await Promise.all([
    getWardForecast(run.id), getWindows(run.id), getPlumes(run.id), getWeather(run.issued_at),
    getSites(), getReceptors(), getStations(run.metrics.stations), getKpis(run), getAlerts(run.id), getNodes(),
    getWardExposure(run.id), getAcceptedAvoided(),
  ]);
  const hours = buildMapHours(windows, plumes, wx);
  const notice = dataNotice(run.data_mode, run.metrics.newest_real_reading, run.issued_at, run.metrics.filled?.stations ?? 0);

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
        {notice && <div className="banner">{notice} <Link href="/data">See the data check</Link>.</div>}
        <section className="stats" aria-label="Ward at a glance">
          {kpiTiles(kpis).map((t) => (
            <div key={t.label} className="panel stat"><span className="v">{t.value}</span><span className="d">{t.label}</span></div>
          ))}
        </section>
        <div className="grid2">
          <section className="panel" aria-label="Plume map">
            <div className="ph"><h2>Plume map</h2><span className="meta">Gaussian plume, hourly</span></div>
            <DustMap center={[ward.center_lon, ward.center_lat]} boundary={ward.boundary} sites={sites} receptors={receptors} stations={stations} nodes={nodes} hours={hours} />
          </section>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <section className="panel" aria-label="Exposure avoided">
            <div className="ph"><h2>Dust kept off people</h2><span className="meta">Next 48 h · modelled</span></div>
            <div className="pb">
              {!ex ? <p className="small muted" style={{ margin: 0 }}>Not worked out for this run yet; the next run adds it.</p> : ex.sites_with_avoid === 0 ? (
                <p className="small" style={{ margin: 0 }}>{ex.sites === 0 ? "No real sites in this run." : <>No real site has an Avoid hour between 06:00 and 22:00 in this forecast, so there is no work to move. Their dust puts <span className="tab">{fmtExposure(ex.without_plan)}</span> person·µg/m³·h on people either way.</>}</p>
              ) : (
                <>
                  <div className="stat" style={{ padding: 0 }}>
                    <span className="v">{Math.round(ex.avoided_pct ?? 0)}%</span>
                    <span className="d">of the dust real sites put on people avoidable if every site follows its plan: <b className="tab">{fmtExposure(ex.avoided)}</b> of <span className="tab">{fmtExposure(ex.without_plan)}</span> person·µg/m³·h, by moving {ex.moved_hours} Avoid {ex.moved_hours === 1 ? "hour" : "hours"} at {ex.sites_with_avoid} {ex.sites_with_avoid === 1 ? "site" : "sites"}{ex.stuck_hours > 0 ? `; ${ex.stuck_hours} more ${ex.stuck_hours === 1 ? "has" : "have"} no better hour that day` : ""}.</span>
                  </div>
                  {ex.avoided_15_pct != null && <p className="small" style={{ margin: "12px 0 0" }}>Where it adds 15 µg/m³ or more: <span className="tab">{Math.round(ex.avoided_15_pct)}%</span> (<span className="tab">{fmtExposure(ex.avoided_15)}</span> of <span className="tab">{fmtExposure(ex.without_15)}</span>).</p>}
                  <p className="small" style={{ margin: "12px 0 0" }}>{accepted.plans === 0 ? "No site has accepted a plan in the last 7 days." : <>Plans accepted in the last 7 days ({accepted.plans}) keep <b className="tab">{fmtExposure(accepted.avoided)}</b> person·µg/m³·h off people, if followed. Not checked on site.</>}</p>
                </>
              )}
              {ex && ex.demo_sites > 0 && <p className="small" style={{ margin: "10px 0 0" }}>Not counted: {ex.demo_sites} demo {ex.demo_sites === 1 ? "site" : "sites"} at approximate positions, which would add <span className="tab">{fmtExposure(ex.demo_avoided)}</span> avoidable.</p>}
              <p className="small muted" style={{ margin: "10px 0 0" }}>{EXPOSURE_DEFINITION}</p>
            </div>
          </section>
          <section className="panel" aria-label="Alerts">
            <div className="ph"><h2>Alerts</h2><span className="meta">Logged, not sent</span></div>
            <div className="pb">
              {alerts.length === 0 ? <p className="small muted">No alerts in this run.</p> : (
                <ul className="list">
                  {alerts.slice(0, 6).map((a) => (
                    <li key={a.id}>
                      <Link href={a.case_id ? "/cases" : `/sites/${a.site_id}`} className="item">
                        <span className="bar" style={{ background: ALERT_TONE[a.kind] }} />
                        <div>
                          <div className="hd"><b>{a.title}</b></div>
                          <p>{a.action}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {alerts.length > 6 && <p className="small muted" style={{ margin: "8px 0 0" }}>{alerts.length - 6} more on the Cases page.</p>}
            </div>
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
                          <div className="hd"><b>{siteLabel(site.id, site.name)}</b></div>
                          <div className="small" style={{ marginTop: 2 }}>Avoid {spanText(sp.from, sp.to)}</div>
                          <p>{sp.rows[0].reason}</p>
                          <p style={{ color: "var(--text)" }}>{moveText(sp)}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
          </div>
        </div>
      </main>
    </>
  );
}
