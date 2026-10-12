import Link from "next/link";
import TopBar from "@/components/TopBar";
import NoRun from "@/components/Empty";
import { logOutcome } from "@/lib/actions";
import { OUTCOMES, routeOrder } from "@/lib/officer";
import { getLatestRun, getOfficerActions, getRanking, getRecentInspections, getWard } from "@/lib/queries";
import { ACTION_LABEL, dayHour } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function OfficerPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const [ranking, todo, recent] = await Promise.all([getRanking(run.id), getOfficerActions(), getRecentInspections()]);
  // Visit the sites with something to look at, nearest first from the ward office.
  const due = ranking.filter((r) => r.score >= 5 || todo.some((t) => t.site_id === r.site_id));
  const stops = routeOrder({ lat: ward.center_lat, lon: ward.center_lon }, due);

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view officer">
        <div>
          <h1>Today&apos;s visits</h1>
          <p className="lede">{stops.length} sites in visiting order from the ward office. Log what you find; the next forecast run re-ranks the list and the agent counts confirmed violations.</p>
        </div>
        {stops.length === 0 && <section className="panel"><div className="pb"><p className="small muted">Nothing needs a visit in this forecast.</p></div></section>}
        <ol className="list">
          {stops.map((r, i) => {
            const mine = todo.filter((t) => t.site_id === r.site_id);
            return (
              <li key={r.site_id} className="panel stop">
                <div className="ph">
                  <h2><span className="tab muted">{i + 1}.</span> {r.site_id} · {r.name}</h2>
                  <span className="meta">rank {r.rank} · {Math.round(r.score)} points</span>
                </div>
                <div className="pb">
                  {r.reasons.map((x) => <p key={x} className="small" style={{ margin: "0 0 4px" }}>{x}</p>)}
                  {mine.length > 0 && <p className="small muted" style={{ margin: "6px 0 0" }}>Open: {mine.map((t) => `${ACTION_LABEL[t.action] ?? t.action} (${t.rule})`).join(", ")}</p>}
                  <p className="small" style={{ margin: "8px 0 12px" }}>
                    <a href={`https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lon}`} target="_blank" rel="noreferrer">Directions</a>
                    {" · "}<Link href={`/sites/${r.site_id}`}>Site page</Link>
                  </p>
                  <form action={logOutcome} className="outcome">
                    <input type="hidden" name="site_id" value={r.site_id} />
                    <fieldset>
                      <legend className="small muted">What did you find?</legend>
                      {Object.entries(OUTCOMES).map(([k, label]) => (
                        <label key={k} className="choice"><input type="radio" name="outcome" value={k} required /> {label}</label>
                      ))}
                    </fieldset>
                    <textarea name="note" rows={2} maxLength={1000} placeholder="Note (optional): what you saw, what you asked for" />
                    <button className="btn primary">Log outcome</button>
                  </form>
                </div>
              </li>
            );
          })}
        </ol>
        <section className="panel">
          <div className="ph"><h2>Logged recently</h2></div>
          <div className="pb">
            {recent.length === 0 ? <p className="small muted">No outcomes logged yet.</p> : (
              <table className="tbl"><thead><tr><th>When</th><th>Site</th><th>Outcome</th><th>Note</th></tr></thead>
                <tbody>{recent.map((x) => (
                  <tr key={x.id}><td>{dayHour(x.at)}</td><td>{x.site_id} · {x.site_name}</td>
                    <td>{OUTCOMES[x.outcome as keyof typeof OUTCOMES] ?? x.outcome}</td><td className="muted">{x.note}</td></tr>
                ))}</tbody></table>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
