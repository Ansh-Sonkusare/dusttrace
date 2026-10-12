import type { Run, Ward } from "@/lib/queries";
import { dayHour } from "@/lib/format";

const MODE: Record<Run["data_mode"], { cls: string; label: string }> = {
  live: { cls: "go", label: "Live data" },
  filled: { cls: "caution", label: "Real stations, recent hours model-filled" },
  mixed: { cls: "caution", label: "Partly synthetic data" },
  synthetic: { cls: "dust", label: "Synthetic data" },
};

export default function TopBar({ ward, run }: { ward: Ward | null; run: Run | null }) {
  return (
    <header className="top">
      <b>{ward?.name ?? "No ward loaded"}</b>
      <div className="sp" />
      {run ? (
        <>
          <span className="small muted">Forecast issued {dayHour(run.issued_at)} IST</span>
          <span className={`pill ${MODE[run.data_mode].cls}`}>{MODE[run.data_mode].label}</span>
        </>
      ) : (
        <span className="pill">No run yet</span>
      )}
    </header>
  );
}
