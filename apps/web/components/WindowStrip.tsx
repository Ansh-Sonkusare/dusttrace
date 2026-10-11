import type { WindowRow } from "@/lib/queries";
import { dayHour, istHour, STATUS_LABEL } from "@/lib/format";

/** One cell per forecast hour. Night hours (22:00–06:00 IST, no dusty work allowed) are dimmed. */
export default function WindowStrip({ rows, tall = false }: { rows: WindowRow[]; tall?: boolean }) {
  return (
    <div className={`strip${tall ? " tall" : ""}`} role="img" aria-label="Safe-Work Windows for the next 48 hours">
      {rows.map((w) => {
        const h = istHour(w.ts);
        const night = h >= 22 || h < 6;
        return <i key={w.ts} className={`${w.status}${night ? " night" : ""}`} title={`${dayHour(w.ts)} IST · ${STATUS_LABEL[w.status]} · ${w.reason}`} />;
      })}
    </div>
  );
}
