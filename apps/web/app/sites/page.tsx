import Link from "next/link";
import TopBar from "@/components/TopBar";
import WindowStrip from "@/components/WindowStrip";
import NoRun from "@/components/Empty";
import { getLatestRun, getSites, getWard, getWindows } from "@/lib/queries";
import { ACTIVITY_LABEL } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function SitesPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [sites, windows] = await Promise.all([getSites(), getWindows(run.id)]);

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Safe-Work Windows</h1>
          <p className="lede">Each cell is one hour. <b>Avoid</b> means the site&apos;s plume would reach a school, hospital or many residents at harmful levels. Dimmed hours are night, when dusty work is not allowed anyway.</p>
        </div>
        <section className="panel">
          <div className="pb">
            <table className="tbl">
              <thead><tr><th>Site</th><th>Activity</th><th style={{ width: "52%" }}>Next 48 hours</th><th>Avoid</th></tr></thead>
              <tbody>
                {sites.map((s) => {
                  const rows = windows.filter((w) => w.site_id === s.id);
                  return (
                    <tr key={s.id}>
                      <td><Link href={`/sites/${s.id}`}><b>{s.id}</b> {s.name}</Link>{s.demo && <span className="pill" style={{ marginLeft: 8 }}>Demo</span>}</td>
                      <td>{ACTIVITY_LABEL[s.activity] ?? s.activity}</td>
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
