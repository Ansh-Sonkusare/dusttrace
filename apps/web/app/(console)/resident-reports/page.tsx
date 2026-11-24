import Link from "next/link";
import TopBar from "@/components/TopBar";
import { reviewReport } from "@/lib/actions";
import { dayShort, hhmm } from "@/lib/format";
import { getLatestRun, getReports, getWard, type CitizenReport } from "@/lib/queries";
import { REPORT_KINDS } from "@/lib/report";
import { siteLabel } from "@/lib/sites";

export const dynamic = "force-dynamic";

const when = (ts: string) => `${dayShort(ts)}, ${hhmm(ts)} IST`;
const kind = (k: string) => REPORT_KINDS[k as keyof typeof REPORT_KINDS] ?? k;

function Place({ r }: { r: CitizenReport }) {
  const spot = r.lat !== null && r.lon !== null && (
    <a href={`https://www.google.com/maps/search/?api=1&query=${r.lat},${r.lon}`} target="_blank" rel="noreferrer" className="tab">
      {r.lat.toFixed(5)}, {r.lon.toFixed(5)}{r.accuracy_m !== null && ` (within ${Math.round(r.accuracy_m)} m)`}
    </a>
  );
  if (r.site_id) return <><Link href={`/sites/${r.site_id}`}>{siteLabel(r.site_id, r.site_name ?? r.site_id)}</Link>{spot && <> · resident at {spot}</>}</>;
  return <>No registered site · {spot}</>;
}

// Residents' reports (F2, F8): the officer checks each one. Verified reports count toward the site's Dust
// Score on the next run; rejected ones stop counting toward the inspection list.
export default async function ResidentReportsPage() {
  const [ward, run, fresh, decided] = await Promise.all([getWard(), getLatestRun(), getReports("new"), getReports("reviewed", 12)]);
  return (
    <>
      <TopBar ward={ward} run={run} />
      <main className="view">
        <div>
          <h1>Resident reports</h1>
          <p className="lede">Dust reported from a site&apos;s QR page, or from a place with no site at <a href="/report-dust">/report-dust</a>. Check each one. A verified report counts against the site&apos;s Dust Score from the next run; a rejected one stops counting toward the inspection list. Photos may show people: keep them inside the office.</p>
        </div>
        <section className="panel">
          <div className="ph"><h2>Waiting for a check</h2><span className="meta">{fresh.length} new</span></div>
          <div className="pb">
            {fresh.length === 0 ? <p className="small muted">No new reports.</p> : (
              <ul className="list">
                {fresh.map((r) => (
                  <li key={r.id} className="item">
                    <span className="bar" style={{ background: "var(--line-2)" }} />
                    <div className="report-body">
                      {r.photo ? (
                        <a href={`/api/photos/${r.id}`} target="_blank" rel="noreferrer">
                          <img src={`/api/photos/${r.id}`} width={r.photo.width} height={r.photo.height} alt={`Photo sent with report ${r.id}`} className="thumb" />
                        </a>
                      ) : <div className="thumb none small muted">No photo</div>}
                      <div>
                        <div className="hd"><b>{kind(r.kind)}</b><span>{when(r.at)}</span></div>
                        {r.note && <p>&ldquo;{r.note}&rdquo;</p>}
                        <p><Place r={r} /></p>
                        <form action={reviewReport} className="decide">
                          <input type="hidden" name="id" value={r.id} />
                          <button className="btn" name="verdict" value="verified" title="It checks out: counts against the site's Dust Score">Verify</button>
                          <button className="btn" name="verdict" value="rejected" title="Not real or not construction dust: stops counting">Reject</button>
                        </form>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="ph"><h2>Checked recently</h2></div>
          <div className="pb">
            {decided.length === 0 ? <p className="small muted">No reports checked yet.</p> : (
              <table className="tbl">
                <thead><tr><th>Sent</th><th>What</th><th>Where</th><th>Verdict</th></tr></thead>
                <tbody>{decided.map((r) => (
                  <tr key={r.id}>
                    <td>{when(r.at)}</td><td>{kind(r.kind)}</td><td><Place r={r} /></td>
                    <td>{r.status === "verified" ? "Verified" : "Rejected"}{r.reviewed_at && <span className="muted">, {when(r.reviewed_at)}</span>}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
