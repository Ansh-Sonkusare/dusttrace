import TopBar from "@/components/TopBar";
import { siteLabel } from "@/lib/sites";
import DustMap from "@/components/DustMap";
import NoRun from "@/components/Empty";
import Link from "next/link";
import { getAlerts, getKpis, getLatestRun, getPlumes, getReceptors, getSites, getStations, getWard, getWardForecast, getWeather, getWindows } from "@/lib/queries";
import { kpiTiles } from "@/lib/kpi";
import { dataNotice } from "@/lib/notice";
import { buildMapHours, spans } from "@/lib/mapHours";
import { dayHour, hhmm } from "@/lib/format";

export const dynamic = "force-dynamic";

const ALERT_TONE = { critical: "var(--avoid)", action: "var(--caution)", receptor: "var(--dust)", sensor: "var(--line-2)" } as const;

export default async function Overview() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);

  const [fc, windows, plumes, wx, sites, receptors, stations, kpis, alerts] = await Promise.all([
    getWardForecast(run.id), getWindows(run.id), getPlumes(run.id), getWeather(run.issued_at),
    getSites(), getReceptors(), getStations(run.metrics.stations), getKpis(run), getAlerts(run.id),
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
            <DustMap center={[ward.center_lon, ward.center_lat]} sites={sites} receptors={receptors} stations={stations} hours={hours} />
          </section>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
        </div>
      </main>
    </>
  );
}
