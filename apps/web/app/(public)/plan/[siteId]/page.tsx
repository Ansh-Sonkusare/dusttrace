import { notFound } from "next/navigation";
import Logo from "@/components/Logo";
import WindowStrip from "@/components/WindowStrip";
import { acceptPlan } from "@/lib/actions";
import { mistSchedule, planSecret, verifySite } from "@/lib/plan";
import { spans } from "@/lib/mapHours";
import { getLastAcceptance, getLatestRun, getSite, getWindows } from "@/lib/queries";
import { dayHour, hhmm, istHour, STATUS_LABEL } from "@/lib/format";

export const dynamic = "force-dynamic";

const until = (ts: string) => hhmm(new Date(new Date(ts).getTime() + 3600_000).toISOString());

// Site manager's plan (PRD F7), opened from a signed link. Shows the next 24 h: when to hold dusty
// work, when misting runs, and an Accept button. No console password; the token limits it to one site.
export default async function PlanPage({ params, searchParams }: {
  params: Promise<{ siteId: string }>; searchParams: Promise<{ t?: string }>;
}) {
  const [{ siteId }, { t = "" }] = await Promise.all([params, searchParams]);
  const secret = planSecret();
  if (!secret || !verifySite(siteId, t, secret)) notFound();
  const [site, run, accepted] = await Promise.all([getSite(siteId), getLatestRun(), getLastAcceptance(siteId)]);
  if (!site || !run) notFound();
  const rows = (await getWindows(run.id, siteId)).slice(0, 24);
  const holds = spans(rows).filter((s) => s.status === "avoid" && istHour(s.from) >= 6 && istHour(s.from) < 22);
  const mist = mistSchedule(rows.filter((r) => { const h = istHour(r.ts); return h >= 6 && h < 22; }));
  const best = spans(rows.filter((r) => r.status === "go" && istHour(r.ts) >= 8 && istHour(r.ts) < 20))
    .sort((a, b) => b.rows.length - a.rows.length).slice(0, 2).sort((a, b) => a.from.localeCompare(b.from));
  const acceptedThisRun = accepted != null && Number(accepted.run_id) === run.id; // pg returns bigint as text

  return (
    <main className="public">
      <header className="pub-head"><Logo /><b>DustTrace</b><span className="muted small">Plan for the site manager</span></header>
      <h1>{site.name}</h1>
      {(site.demo || run.data_mode !== "live") && <div className="banner">Demo site for the DustTrace prototype; the forecast uses partly synthetic data.</div>}
      <section className="panel">
        <div className="ph"><h2>Next 24 hours</h2><span className="meta">From {dayHour(rows[0]?.ts ?? run.issued_at)}</span></div>
        <div className="pb"><WindowStrip rows={rows} tall /></div>
      </section>
      <section className="panel">
        <div className="ph"><h2>Hold dusty work</h2></div>
        <div className="pb">
          {holds.length === 0 ? <p className="small">No hold needed. Dusty work can go ahead, with the usual water spraying.</p> : (
            <ul className="list">{holds.map((s) => (
              <li key={s.from} className="item"><span className="bar" style={{ background: "var(--avoid)" }} />
                <div><div className="hd"><b>{STATUS_LABEL.avoid} {dayHour(s.from)}–{until(s.to)}</b></div><p>{s.rows[0].reason}</p></div></li>
            ))}</ul>
          )}
          {best.length > 0 && <p className="small" style={{ margin: "12px 0 0" }}>Best hours for demolition, digging and cutting: {best.map((s) => `${dayHour(s.from)}–${until(s.to)}`).join(" and ")}.</p>}
        </div>
      </section>
      {mist.length > 0 && (
        <section className="panel">
          <div className="ph"><h2>Misting</h2></div>
          <div className="pb">
            <ul className="list">{mist.map((m) => (
              <li key={m.from} className="item"><span className="bar" style={{ background: "var(--text-3)" }} />
                <div><div className="hd"><b>{dayHour(m.from)}–{hhmm(m.to)}</b></div><p>Run the mist cannon or sprinklers along the boundary, starting 90 minutes before the hold.</p></div></li>
            ))}</ul>
          </div>
        </section>
      )}
      <section className="panel">
        <div className="pb">
          {acceptedThisRun ? (
            <p className="small">Plan accepted {dayHour(accepted!.accepted_at)}. Thank you; following it raises your site&apos;s Dust Score.</p>
          ) : (
            <form action={acceptPlan}>
              <input type="hidden" name="site_id" value={site.id} />
              <input type="hidden" name="t" value={t} />
              <button className="btn primary big">Accept plan</button>
              <p className="small muted" style={{ margin: "10px 0 0" }}>Accepting tells the ward you will hold dusty work and mist as shown. Following it counts toward your Dust Score.</p>
            </form>
          )}
        </div>
      </section>
      <footer className="small muted">DustTrace · Team ARA IGNITE</footer>
    </main>
  );
}
