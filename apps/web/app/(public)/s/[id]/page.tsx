import { notFound } from "next/navigation";
import Logo from "@/components/Logo";
import WindowStrip from "@/components/WindowStrip";
import ReportForm from "@/components/ReportForm";
import { getDustScores, getLatestRun, getSite, getWard, getWindows } from "@/lib/queries";
import { REPORT_KINDS } from "@/lib/report";
import { SCORE_BAND, SCORE_PART } from "@/lib/format";

export const dynamic = "force-dynamic";

const MESSAGE: Record<string, string> = {
  sent: "Thank you. Your report went to the ward environment officer.",
};

// Public page for residents, opened from the QR code on the site's LED board (PRD F8).
export default async function PublicSitePage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ r?: string }>;
}) {
  const [{ id }, { r }] = await Promise.all([params, searchParams]);
  const site = await getSite(id);
  const [run, ward] = await Promise.all([getLatestRun(site?.ward_id), getWard(site?.ward_id)]);
  if (!site) notFound();
  const [scores, windows] = run ? await Promise.all([getDustScores(run.id, id), getWindows(run.id, id)]) : [[], []];
  const s = scores[0];
  const band = s ? SCORE_BAND[s.band] : null;

  return (
    <main className="public">
      <header className="pub-head"><Logo /><b>DustTrace</b><span className="muted small">Construction dust in {ward?.name ?? "the ward"}</span></header>
      <h1>{site.name}</h1>
      {(site.demo || run?.data_mode !== "live") && (
        <div className="banner">Demo site for the DustTrace prototype. The score uses simulated monitor data and is not an official rating.</div>
      )}
      {r && MESSAGE[r] && <div className={`banner ${r === "sent" ? "ok" : ""}`} role="status">{MESSAGE[r]}</div>}

      <section className="panel">
        <div className="pb score">
          {s && band ? (
            <>
              <div className="score-v"><span className="tab">{Math.round(s.score)}</span><small>/100</small></div>
              <div>
                <span className={`pill ${band.tone}`}>{band.label}</span>
                <p className="small" style={{ margin: "8px 0 0" }}>{band.meaning}</p>
              </div>
            </>
          ) : <p className="small muted">No score yet.</p>}
        </div>
        {s && (
          <div className="pb" style={{ paddingTop: 0 }}>
            <ul className="parts">
              {Object.entries(SCORE_PART).map(([k, part]) => {
                const got = s.components[k as keyof typeof s.components] ?? 0;
                return (
                  <li key={k}>
                    <span>{part.label}</span>
                    <span className="tab muted">{Math.round(got)} of {part.max}</span>
                    <span className="track"><span style={{ width: `${(got / part.max) * 100}%` }} /></span>
                  </li>
                );
              })}
            </ul>
            {s.notes.map((n) => <p key={n} className="small muted" style={{ margin: "8px 0 0" }}>{n}</p>)}
          </div>
        )}
      </section>

      {windows.length > 0 && (
        <section className="panel">
          <div className="ph"><h2>When this site plans dusty work</h2></div>
          <div className="pb">
            <WindowStrip rows={windows.slice(0, 24)} tall />
            <p className="small muted" style={{ margin: "8px 0 0" }}>Next 24 hours. Green: dusty work is fine. Amber: take care. Red: dusty work should wait, because dust would reach a school, hospital or homes.</p>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="ph"><h2>Report dust from this site</h2></div>
        <div className="pb">
          <ReportForm siteId={site.id} kinds={REPORT_KINDS} />
          <p className="small muted" style={{ margin: "10px 0 0" }}>Reports go to the ward environment officer. An officer checks them before they count toward the score. We keep no name or number: only your location if you share it, and a scrambled code of your connection to stop spam. A photo is shrunk on your phone with its hidden details (such as location tags) removed, and only the ward officer sees it.</p>
          <p className="small muted" style={{ margin: "8px 0 0" }}>Dust from a place with no DustTrace board? <a href="/report-dust">Report that place</a>.</p>
        </div>
      </section>
      <footer className="small muted">DustTrace · Team ARA IGNITE</footer>
    </main>
  );
}
