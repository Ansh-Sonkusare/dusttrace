import Link from "next/link";
import { notFound } from "next/navigation";
import TopBar from "@/components/TopBar";
import WindowStrip from "@/components/WindowStrip";
import NoRun from "@/components/Empty";
import TrustPill from "@/components/TrustPill";
import { planSecret, signSite } from "@/lib/plan";
import { getAudits, getDustScores, getLatestRun, getSite, getSiteExposures, getWard, getWindows } from "@/lib/queries";
import { spans } from "@/lib/mapHours";
import { ACTIVITY_LABEL, dayHour, FAULT_LABEL, hhmm, istHour, SCORE_BAND, STATUS_LABEL, TRUST_TONE } from "@/lib/format";

export const dynamic = "force-dynamic";

const end = (ts: string) => hhmm(new Date(new Date(ts).getTime() + 3600_000).toISOString());

export default async function SitePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [ward, run, site] = await Promise.all([getWard(), getLatestRun(), getSite(id)]);
  if (!site) notFound();
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [rows, exposures, audits, scores] = await Promise.all([getWindows(run.id, id), getSiteExposures(run.id, id), getAudits(run.id, id), getDustScores(run.id, id)]);
  const audit = audits[0];
  const dust = scores[0];
  const day = rows.filter((r) => { const h = istHour(r.ts); return h >= 8 && h < 20; });
  const goSpans = spans(day.filter((r) => r.status === "go")).sort((a, b) => b.rows.length - a.rows.length).slice(0, 3)
    .sort((a, b) => a.from.localeCompare(b.from));
  const holds = spans(rows).filter((s) => s.status !== "go");

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <p className="small"><Link href="/sites" className="muted">Sites</Link></p>
          <h1>{site.id} · {site.name}</h1>
          <p className="lede">{ACTIVITY_LABEL[site.activity] ?? site.activity}, about {Math.round(site.area_m2).toLocaleString("en-IN")} m² active{site.developer ? `, ${site.developer}` : ""}.{site.demo ? " Demo site for the prototype." : ""}</p>
        </div>
        <section className="panel">
          <div className="ph"><h2>Next 48 hours</h2><span className="meta">Hover a cell for the reason</span></div>
          <div className="pb"><WindowStrip rows={rows} tall /></div>
        </section>
        <div className="grid2">
          <section className="panel">
            <div className="ph"><h2>Hold or take care</h2><span className="meta">{holds.length} periods</span></div>
            <div className="pb">
              {holds.length === 0 ? <p className="small muted">No holds. All forecast hours are Go.</p> : (
                <ul className="list">
                  {holds.map((s) => (
                    <li key={s.from} className="item">
                      <span className="bar" style={{ background: `var(--${s.status})` }} />
                      <div>
                        <div className="hd"><b>{STATUS_LABEL[s.status]}</b> {dayHour(s.from)}–{end(s.to)}</div>
                        <p>{s.rows.reduce((a, b) => (b.exposed_people > a.exposed_people ? b : a)).reason}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <section className="panel">
              <div className="ph"><h2>Best hours for dusty work</h2></div>
              <div className="pb">
                {goSpans.length === 0 ? <p className="small muted">No Go hours between 08:00 and 20:00 in this forecast.</p> : (
                  <ul className="list">{goSpans.map((s) => (
                    <li key={s.from} className="item"><span className="bar" style={{ background: "var(--go)" }} />
                      <div><div className="hd"><b>{dayHour(s.from)}–{end(s.to)}</b> {s.rows.length} h</div></div></li>
                  ))}</ul>
                )}
              </div>
            </section>
            {dust && (
              <section className="panel">
                <div className="ph"><h2>Dust Score</h2><span className="meta"><span className={`pill ${SCORE_BAND[dust.band].tone}`}><span className="tab">{Math.round(dust.score)}</span> {SCORE_BAND[dust.band].label}</span></span></div>
                <div className="pb">
                  <p className="small muted" style={{ marginTop: 0 }}>{SCORE_BAND[dust.band].meaning} Shown to residents on the site board through a QR code.</p>
                  <p className="small" style={{ marginBottom: 0 }}><a href={`/s/${site.id}`}>Public page</a> · <a href={`/api/qr/${site.id}`} download={`dusttrace-site-${site.id}.svg`}>QR code for the board</a>{planSecret() ? <> · <a href={`/plan/${site.id}?t=${signSite(site.id, planSecret()!)}`}>Site manager&apos;s plan link</a></> : null}</p>
                </div>
              </section>
            )}
            <section className="panel">
              <div className="ph"><h2>Site sensor</h2><span className="meta"><TrustPill audit={audit} /></span></div>
              <div className="pb">
                {!audit ? <p className="small muted">No dust monitor registered. An active site without one is added to the inspection list (D6).</p> : (
                  <>
                    <p className="small muted">{audit.vendor ?? "Unknown make"}{audit.has_relay ? ", can switch misting remotely" : ""}. {audit.simulated ? `Simulated from real ambient data; injected fault: ${FAULT_LABEL[audit.injected_fault ?? "none"] ?? audit.injected_fault}.` : "Live feed."}</p>
                    {audit.reasons.length === 0 ? <p className="small">All six checks passed: it reads above the stations while the site works, tracks the wind, and holds calibration.</p> : (
                      <ul className="list">{audit.reasons.map((r) => (
                        <li key={r} className="item"><span className="bar" style={{ background: `var(--${TRUST_TONE[audit.band]})` }} /><div><p style={{ margin: 0 }}>{r}</p></div></li>
                      ))}</ul>
                    )}
                  </>
                )}
              </div>
            </section>
            <section className="panel">
              <div className="ph"><h2>Who the plume reaches</h2></div>
              <div className="pb">
                {exposures.length === 0 ? <p className="small muted">No receptor gets more than 15 µg/m³ from this site.</p> : (
                  <table className="tbl"><thead><tr><th>Place</th><th>Hours</th><th>Peak added</th></tr></thead>
                    <tbody>{exposures.map((e) => (
                      <tr key={e.receptor_id}><td>{e.name}</td><td className="tab">{e.hours}</td><td className="tab">{Math.round(e.peak)}</td></tr>
                    ))}</tbody></table>
                )}
              </div>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}
