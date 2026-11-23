import Logo from "@/components/Logo";
import ReportForm from "@/components/ReportForm";
import { REPORT_ERROR, REPORT_KINDS } from "@/lib/report";
import { WARDS } from "@/lib/wards";

export const dynamic = "force-dynamic";

// ?r=… after a form posted without JavaScript: thanks, or why the report was refused.
const MESSAGE: Record<string, string> = {
  sent: "Thank you. Your report went to the ward environment officer.",
  ...REPORT_ERROR,
};

// Public page for dust from a place with no registered site (PRD F2). The resident's position is required;
// nearby reports are grouped into one place that an officer can confirm as a site.
export default async function ReportDustPage({ searchParams }: { searchParams: Promise<{ r?: string }> }) {
  const { r } = await searchParams;
  return (
    <main className="public">
      <header className="pub-head"><Logo /><b>DustTrace</b><span className="muted small">Construction dust in {WARDS.map((w) => w.name).join(" and ")}</span></header>
      <h1>Report construction dust</h1>
      <p className="small muted" style={{ margin: 0 }}>For dust from a place with no DustTrace board. If the site has a board, scan its QR code instead.</p>
      {r && Object.hasOwn(MESSAGE, r) && <div className={`banner ${r === "sent" ? "ok" : ""}`} role="status">{MESSAGE[r]}</div>}
      <section className="panel">
        <div className="pb">
          <ReportForm kinds={REPORT_KINDS} />
          <p className="small muted" style={{ margin: "10px 0 0" }}>Reports go to the ward environment officer, who looks at places several people report. We keep no name or number, only your location for this report and a scrambled code of your connection to stop spam. A photo is shrunk on your phone with its hidden details (such as location tags) removed, and only the ward officer sees it.</p>
        </div>
      </section>
      <footer className="small muted">DustTrace · Team ARA IGNITE</footer>
    </main>
  );
}
