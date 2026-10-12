import { monitorLabel } from "@/lib/sites";
import type { Audit } from "@/lib/queries";
import { TRUST_LABEL, TRUST_TONE } from "@/lib/format";

export default function TrustPill({ audit, status }: { audit?: Audit; status?: string }) {
  if (!audit) return <span className="pill">{status === "not_connected" ? monitorLabel(status) : "No sensor"}</span>;
  return (
    <span className={`pill ${TRUST_TONE[audit.band]}`} title={audit.reasons.join(" ") || "All checks passed."}>
      <span className="tab">{Math.round(audit.score)}</span> {TRUST_LABEL[audit.band]}
    </span>
  );
}
