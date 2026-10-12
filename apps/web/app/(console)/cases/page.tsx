import Link from "next/link";
import { siteLabel } from "@/lib/sites";
import TopBar from "@/components/TopBar";
import NoRun from "@/components/Empty";
import { decideAction } from "@/lib/actions";
import { getLatestRun, getOpenCases, getWard, type CaseAction } from "@/lib/queries";
import { ACTION_LABEL, CAUSE_LABEL, caseId, dayHour, ROUTE_LABEL, STATE_LABEL, STATUS_WORD } from "@/lib/format";

export const dynamic = "force-dynamic";

const TONE: Record<string, string> = { proposed: "dust", approved: "go", declined: "", expired: "avoid", requested: "caution" };

function ActionRow({ a }: { a: CaseAction }) {
  return (
    <li className="item">
      <span className="bar" style={{ background: a.status === "proposed" ? "var(--dust)" : "var(--line-2)" }} />
      <div>
        <div className="hd">
          <b>{ACTION_LABEL[a.action] ?? a.action}</b>
          <span>{a.rule} · {ROUTE_LABEL[a.route]}</span>
          <span className={`pill ${TONE[a.status] ?? ""}`} style={{ marginLeft: "auto" }}>{STATUS_WORD[a.status] ?? a.status}</span>
        </div>
        <p>{a.reason}{a.deadline && a.status === "requested" ? ` Reply by ${dayHour(a.deadline)}.` : ""}</p>
        {a.status === "proposed" && (
          <form action={decideAction} className="decide">
            <input type="hidden" name="id" value={a.id} />
            <button className="btn primary" name="verdict" value="approved">Approve</button>
            <button className="btn" name="verdict" value="declined">Decline</button>
          </form>
        )}
      </div>
    </li>
  );
}

export default async function CasesPage() {
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return (<><TopBar ward={ward} run={run} /><main className="view"><NoRun /></main></>);
  const cases = await getOpenCases();

  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Cases</h1>
          <p className="lede">Every trigger opens a case. The Dust Response Agent weighs the likely cause and picks actions under dust rules D1–D10, each with who has to approve it. It never takes enforcement on one signal alone, never assumes a reply, and a stop-work order is only ever a recommendation. Alerts are logged, not sent, in this prototype.</p>
        </div>
        {cases.length === 0 ? <section className="panel"><div className="pb"><p className="small muted">No open cases. Nothing triggered in the latest run.</p></div></section> : cases.map((c) => {
          const final = c.actions.filter((a) => a.phase === "final");
          const [top, second] = c.hypotheses;
          return (
            <section key={c.id} className="panel">
              <div className="ph">
                <h2><Link href={`/sites/${c.site_id}`}>{siteLabel(c.site_id, c.site_name)}</Link></h2>
                <span className="meta">{caseId(c.id)} · opened {dayHour(c.opened_at)} · <span className="pill">{STATE_LABEL[c.state] ?? c.state}</span></span>
              </div>
              <div className="pb grid-case">
                <div>
                  <p className="small muted" style={{ margin: "0 0 8px" }}>Why: {c.triggers.map((t) => t.replaceAll("_", " ")).join(", ")}. Evidence: {c.signals.join(", ") || "none yet"}.</p>
                  <ul className="list">{final.map((a) => <ActionRow key={a.id} a={a} />)}</ul>
                </div>
                <div className="small">
                  <p style={{ margin: "0 0 6px" }}><b>Likely cause</b></p>
                  <p className="muted" style={{ margin: "0 0 12px" }}>
                    {top ? `${CAUSE_LABEL[top[0]] ?? top[0]} ${Math.round(top[1] * 100)}%` : "–"}
                    {second ? `, then ${CAUSE_LABEL[second[0]] ?? second[0]} ${Math.round(second[1] * 100)}%` : ""}
                  </p>
                  <p style={{ margin: "0 0 6px" }}><b>What changed</b></p>
                  <p className="muted" style={{ margin: "0 0 12px" }}>{c.what_changed}</p>
                  <p style={{ margin: "0 0 6px" }}><b>Next</b></p>
                  <p className="muted" style={{ margin: 0 }}>{c.stop_reason}</p>
                </div>
              </div>
            </section>
          );
        })}
      </main>
    </>
  );
}
