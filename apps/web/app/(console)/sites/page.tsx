import Link from "next/link";
import TopBar from "@/components/TopBar";
import WindowStrip from "@/components/WindowStrip";
import NoRun from "@/components/Empty";
import TrustPill from "@/components/TrustPill";
import { getAudits, getLatestRun, getSites, getWard, getWindows } from "@/lib/queries";
import { ACTIVITY_LABEL } from "@/lib/format";
import { sourceLabel } from "@/lib/sites";

export const dynamic = "force-dynamic";

export default async function SitesPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [sites, windows, audits] = await Promise.all([getSites(), getWindows(run.id), getAudits(run.id)]);
  const bench = run.metrics.audit;
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
          <p className="lede">Sensor trust scores each site&apos;s own dust monitor against the stations and the wind. Until BMC shares the site feed, the monitors are simulated from real ambient data with faults injected{bench ? <>; this run&apos;s audit caught {Math.round(bench.recall * 100)}% of injected faults at {Math.round(bench.precision * 100)}% precision on {bench.n} simulated sensors</> : null}.</p>
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
      </main>
    </>
  );
}
