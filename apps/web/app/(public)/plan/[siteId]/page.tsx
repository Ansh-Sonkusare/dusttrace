import { notFound } from "next/navigation";
import Logo from "@/components/Logo";
import WindowStrip from "@/components/WindowStrip";
import { acceptPlan } from "@/lib/actions";
import { mistSchedule, planSecret, verifySite } from "@/lib/plan";
import { fmtExposure, moveText, planGain } from "@/lib/exposure";
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
  const [site, accepted] = await Promise.all([getSite(siteId), getLastAcceptance(siteId)]);
  const run = site ? await getLatestRun(site.ward_id) : null;
  if (!site || !run) notFound();
  const rows = (await getWindows(run.id, siteId)).slice(0, 24);
  const holds = spans(rows).filter((s) => s.status === "avoid" && istHour(s.from) >= 6 && istHour(s.from) < 22);
  const mist = mistSchedule(rows.filter((r) => { const h = istHour(r.ts); return h >= 6 && h < 22; }));
  const best = spans(rows.filter((r) => r.status === "go" && istHour(r.ts) >= 8 && istHour(r.ts) < 20))
    .sort((a, b) => b.rows.length - a.rows.length).slice(0, 2).sort((a, b) => a.from.localeCompare(b.from));
  const acceptedThisRun = accepted != null && Number(accepted.run_id) === run.id; // pg returns bigint as text
  const gain = planGain(rows);

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
                <div><div className="hd"><b>{STATUS_LABEL.avoid} {dayHour(s.from)}–{until(s.to)}</b></div><p>{s.rows[0].reason}</p>
                  <p style={{ color: "var(--text)" }}>{moveText(s)}</p></div></li>
            ))}</ul>
          )}
          {best.length > 0 && <p className="small" style={{ margin: "12px 0 0" }}>Best hours for demolition, digging and cutting: {best.map((s) => `${dayHour(s.from)}–${until(s.to)}`).join(" and ")}.</p>}
        </div>
      </section>
      <section className="panel">
        <div className="ph"><h2>What the plan keeps off your neighbours</h2></div>
        <div className="pb">
          <p className="small" style={{ marginTop: 0 }}>
            {gain.avoided > 0
              ? <>Moving the dusty work as shown cuts the dust your site puts on the people around it by about <b>{Math.round(gain.pct ?? 0)}%</b> over the next 24 hours, counting the faint dust that drifts furthest. Where your dust is thick (15 µg/m³ or more) the cut is {Math.round(gain.pct_15 ?? 0)}%. In the hours to avoid, it would reach up to {gain.people.toLocaleString("en-IN")} people at once.{gain.stuck > 0 ? ` For ${gain.stuck} of those hours there is no better hour that day.` : ""}</>
              : gain.without === 0
                ? "Your site's dust is not forecast to reach homes, schools or hospitals during working hours in the next 24 hours."
                : gain.stuck > 0
                  ? "There is no better hour on the same day for the work in the hours to avoid. Holding it to another day is what keeps the dust off your neighbours."
                  : "No hour to avoid between 06:00 and 22:00 in the next 24 hours, so there is no work to move."}
          </p>
          {gain.without > 0 && <p className="small muted" style={{ margin: 0 }}>Counted as people × the dust your site adds where they live, study or are treated (µg/m³) × hours: <span className="tab">{fmtExposure(gain.without)}</span> person·µg/m³·h if dusty work runs every hour from 06:00 to 22:00, <span className="tab">{fmtExposure(gain.with)}</span> if you follow the plan. Worked out from the weather forecast, not measured.</p>}
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
