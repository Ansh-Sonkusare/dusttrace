import Link from "next/link";
import { notFound } from "next/navigation";
import TopBar from "@/components/TopBar";
import WindowStrip from "@/components/WindowStrip";
import NoRun from "@/components/Empty";
import { getLatestRun, getSite, getSiteExposures, getWard, getWindows } from "@/lib/queries";
import { spans } from "@/lib/mapHours";
import { ACTIVITY_LABEL, dayHour, hhmm, istHour, STATUS_LABEL } from "@/lib/format";

export const dynamic = "force-dynamic";

const end = (ts: string) => hhmm(new Date(new Date(ts).getTime() + 3600_000).toISOString());

export default async function SitePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [ward, run, site] = await Promise.all([getWard(), getLatestRun(), getSite(id)]);
  if (!site) notFound();
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [rows, exposures] = await Promise.all([getWindows(run.id, id), getSiteExposures(run.id, id)]);
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
