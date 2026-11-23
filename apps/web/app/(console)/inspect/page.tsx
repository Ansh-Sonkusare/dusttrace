import Link from "next/link";
import TopBar from "@/components/TopBar";
import NoRun from "@/components/Empty";
import { getCandidates, getLatestRun, getRanking, getReportedPlaces, getWard } from "@/lib/queries";
import { decideCandidate, decidePlace } from "@/lib/actions";
import { dayShort, hhmm } from "@/lib/format";
import { PLACE_DAYS, PLACE_RADIUS_M } from "@/lib/places";
import { REPORT_KINDS } from "@/lib/report";
import { sourceLabel, siteLabel } from "@/lib/sites";

export const dynamic = "force-dynamic";

// "S2B_42QZG_20260210_0_L2A" -> "Feb 2026"
const sceneMonth = (id?: string) => {
  const d = id?.split("_")[2];
  return d && d.length === 8 ? new Date(`${d.slice(0, 4)}-${d.slice(4, 6)}-01`).toLocaleString("en-GB", { month: "short", year: "numeric" }) : "";
};

const PARTS = [
  ["upwind", "Upwind of a station"],
  ["trust", "Monitor not trusted"],
  ["unsensored", "No monitor"],
  ["reports", "Citizen reports"],
  ["violations", "Past violations"],
] as const;

export default async function InspectPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [rows, sat, places] = await Promise.all([getRanking(run.id), getCandidates(), getReportedPlaces()]);
  const max = Math.max(1, ...rows.map((r) => r.score));

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Inspect today</h1>
          <p className="lede">Sites ranked for a visit. The score adds up where the wind carries dust toward the stations in the next 24 hours, how far each site&apos;s own monitor can be trusted, whether it has one at all, citizen reports and past violations. Each site shows its two biggest reasons.</p>
        </div>
        <section className="panel">
          <div className="pb">
            {rows.length === 0 ? <p className="small muted">This run has no ranking yet.</p> : (
              <ol className="list">
                {rows.map((r) => (
                  <li key={r.site_id}>
                    <Link href={`/sites/${r.site_id}`} className="item rank">
                      <span className="bar" style={{ background: r.rank <= 3 ? "var(--dust)" : "var(--line-2)" }} />
                      <div>
                        <div className="hd">
                          <b className="tab">{r.rank}</b>
                          <b>{siteLabel(r.site_id, r.name)}</b>
                          {sourceLabel(r) && <span className="pill">{sourceLabel(r)}</span>}
                          <span className="tab" style={{ marginLeft: "auto" }}>{Math.round(r.score)} {Math.round(r.score) === 1 ? "point" : "points"}</span>
                        </div>
                        <div className="meter" aria-hidden="true">
                          {PARTS.map(([k]) => r.components[k] > 0 && (
                            <span key={k} className={`seg ${k}`} style={{ width: `${(r.components[k] / max) * 100}%` }} />
                          ))}
                        </div>
                        {r.reasons.map((x) => <p key={x}>{x}</p>)}
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
            <p className="small muted" style={{ marginTop: 12 }}>
              {PARTS.map(([k, label], i) => <span key={k}>{i > 0 && " · "}<span className={`key ${k}`} /> {label}</span>)}
            </p>
          </div>
        </section>
        <section className="panel">
          <div className="ph"><h2>Reported by residents</h2><span className="meta">Places with no registered site, last {PLACE_DAYS} days</span></div>
          <div className="pb">
            {places.length === 0 ? (
              <p className="small muted" style={{ margin: 0 }}>No reports from places without a site. Residents report them at <a href="/report-dust">/report-dust</a>.</p>
            ) : (
              <>
                <p className="small muted" style={{ marginTop: 0 }}>
                  Reports within about {PLACE_RADIUS_M} m of each other are one place. They are not checked yet, so look before acting (photos are on <Link href="/resident-reports">Resident reports</Link>).
                  Confirming a place adds it to the site list and moves its reports to that site; the next run gives it Safe-Work Windows.
                </p>
                <table className="tbl">
                  <thead><tr><th>Where</th><th>Reports</th><th>What residents saw</th><th>Latest</th><th></th><th></th></tr></thead>
                  <tbody>
                    {places.map((p) => (
                      <tr key={p.ids[0]}>
                        <td className="tab">{p.lat.toFixed(4)}, {p.lon.toFixed(4)}</td>
                        <td className="tab">{p.count}{p.photos > 0 && <span className="muted">, {p.photos} with a photo</span>}</td>
                        <td>{p.kinds.map((k) => REPORT_KINDS[k as keyof typeof REPORT_KINDS] ?? k).join("; ")}</td>
                        <td>{dayShort(p.last_at)}, {hhmm(p.last_at)}</td>
                        <td><a href={`https://www.google.com/maps/@${p.lat},${p.lon},300m/data=!3m1!1e3`} target="_blank" rel="noreferrer">Satellite view</a></td>
                        <td>
                          <form action={decidePlace} className="decide">
                            <input type="hidden" name="id" value={p.ids[0]} />
                            <button className="btn" name="verdict" value="confirmed" title="Add it to the site list; the next run plans windows for it">Confirm site</button>
                            <button className="btn" name="verdict" value="rejected" title="Not construction: reject its reports">Reject</button>
                          </form>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </section>
        {sat.total > 0 && (
          <section className="panel">
            <div className="ph"><h2>Found from satellite</h2><span className="meta">Sentinel-2, {sceneMonth(sat.unmatched[0]?.scene_before)} vs {sceneMonth(sat.unmatched[0]?.scene_after)}</span></div>
            <div className="pb">
              <p className="small muted" style={{ marginTop: 0 }}>
                Ground that turned from green to bare soil over the year. {sat.matched.length > 0 && <>Near known sites {sat.matched.join(", ")}, which confirms they are active (a second signal for the agent). </>}
                The largest patches not on the site list are below. They are unverified: some will be roads, fields drying out or finished buildings, so look before acting. Confirming one adds it to the site list; the next run gives it Safe-Work Windows.
              </p>
              <table className="tbl">
                <thead><tr><th>Where</th><th>Changed area</th><th></th><th></th></tr></thead>
                <tbody>
                  {sat.unmatched.map((c) => (
                    <tr key={c.id}>
                      <td className="tab">{c.lat.toFixed(4)}, {c.lon.toFixed(4)}</td>
                      <td className="tab">{Math.round(c.area_m2 / 100) / 100} ha</td>
                      <td><a href={`https://www.google.com/maps/@${c.lat},${c.lon},300m/data=!3m1!1e3`} target="_blank" rel="noreferrer">Satellite view</a></td>
                      <td>
                        <form action={decideCandidate} className="decide">
                          <input type="hidden" name="id" value={c.id} />
                          <button className="btn" name="verdict" value="confirmed" title="Add it to the site list; the next run plans windows for it">Confirm site</button>
                          <button className="btn" name="verdict" value="rejected" title="Not construction: hide it">Reject</button>
                        </form>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </>
  );
}
