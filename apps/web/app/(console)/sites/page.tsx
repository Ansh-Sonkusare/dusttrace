import Link from "next/link";
import TopBar from "@/components/TopBar";
import WindowStrip from "@/components/WindowStrip";
import NoRun from "@/components/Empty";
import TrustPill from "@/components/TrustPill";
import { getAudits, getLatestRun, getSites, getWard, getWindows } from "@/lib/queries";
import { ACTIVITY_LABEL, dayShort } from "@/lib/format";
import { sourceLabel } from "@/lib/sites";
import { ambientNote, benchmarkTable, faultNotes } from "@/lib/audit";

export const dynamic = "force-dynamic";

export default async function SitesPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [sites, windows, audits] = await Promise.all([getSites(), getWindows(run.id), getAudits(run.id)]);
  const bench = run.metrics.audit;
  const table = benchmarkTable(bench);
  // Only the sites this run covered (demo sites can be switched off in the engine).
  const inRun = new Set(windows.map((w) => w.site_id));
  const shown = inRun.size ? sites.filter((s) => inRun.has(s.id)) : sites;

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Safe-Work Windows</h1>
          <p className="lede">Each cell is one hour. <b>Avoid</b> means the site&apos;s plume would reach a school, hospital or many residents at harmful levels. Dimmed hours are night, when dusty work is not allowed anyway.</p>
          <p className="lede">Sensor trust scores each site&apos;s own dust monitor against its nearest station and the wind. Until BMC shares the site feed, the monitors are simulated from real ambient data with faults injected{bench?.n ? <>; this run&apos;s audit caught {Math.round(bench.recall * 100)}% of injected faults at {Math.round(bench.precision * 100)}% precision on {bench.n} simulated sensors</> : null}.</p>
        </div>
        <section className="panel">
          <div className="pb">
            <table className="tbl">
              <thead><tr><th>Site</th><th>Activity</th><th>Sensor trust</th><th style={{ width: "46%" }}>Next 48 hours</th><th>Avoid</th></tr></thead>
              <tbody>
                {shown.map((s) => {
                  const rows = windows.filter((w) => w.site_id === s.id);
                  return (
                    <tr key={s.id}>
                      <td><Link href={`/sites/${s.id}`}>{s.id.length <= 3 ? <><b>{s.id}</b> {s.name}</> : s.name}</Link>{sourceLabel(s) && <span className="pill" style={{ marginLeft: 8 }}>{sourceLabel(s)}</span>}</td>
                      <td>{ACTIVITY_LABEL[s.activity] ?? s.activity}</td>
                      <td><TrustPill audit={audits.find((a) => a.site_id === s.id)} status={s.sensor_status} /></td>
                      <td><WindowStrip rows={rows} /></td>
                      <td className="tab">{rows.filter((r) => r.status === "avoid").length} h</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <div className="ph"><h2>How well the audit finds faults</h2><span className="meta">Simulated sensors</span></div>
          <div className="pb">
            {!table ? <p className="small muted">Not enough data: this run had no measured station readings in the audit window, so no sensors were simulated or scored.</p> : (
              <>
                <p className="small muted">{ambientNote(bench!)} {bench!.n} simulated site sensors, each built on its nearest station&apos;s measured PM10 and the weather over the week to {bench!.as_of ? dayShort(bench!.as_of) : "this run"}, with one known fault injected in rotation; half their sites count as active in Sentinel-2 imagery. The share of each fault&apos;s sensors that each method flags; a fault changed the readings when it moved at least 6 hours of the week by more than 5%. Only the rule checks set the trust score; the Isolation Forest is shown for comparison, because it also flags healthy sensors that sit in their own site&apos;s plume.</p>
                <div style={{ overflowX: "auto" }}>
                  <table className="tbl">
                    <thead><tr><th>Injected fault</th><th>Sensors</th><th>Changed the readings</th>{table.methods.map((m) => <th key={m.key}>{m.label}</th>)}</tr></thead>
                    <tbody>
                      {table.faults.map((f) => (
                        <tr key={f.fault}><td>{f.label}</td><td className="tab">{f.sensors ?? "–"}</td><td className="tab">{f.shown ?? "–"}</td>{f.rates.map((r, i) => <td key={i} className="tab">{r}</td>)}</tr>
                      ))}
                      <tr><td>No fault, flagged anyway</td><td className="tab">{table.healthy.sensors ?? "–"}</td><td />{table.healthy.rates.map((r, i) => <td key={i} className="tab">{r}</td>)}</tr>
                      <tr><td><b>Precision</b></td><td /><td />{table.precision.map((r, i) => <td key={i} className="tab"><b>{r}</b></td>)}</tr>
                      <tr><td><b>Recall</b></td><td /><td />{table.recall.map((r, i) => <td key={i} className="tab"><b>{r}</b></td>)}</tr>
                    </tbody>
                  </table>
                </div>
                {faultNotes(bench!).length > 0 && <p className="small muted">{faultNotes(bench!).join(" ")}</p>}
              </>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
