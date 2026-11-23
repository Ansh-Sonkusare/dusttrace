// The sensor audit's benchmark (F1): how well each method finds the faults injected into 50 simulated
// sensors. Pure, so it's unit-tested; the Sites page renders it.

import { FAULT_LABEL } from "./format";

interface Rates { precision: number; recall: number; detected?: Record<string, number> }
export interface AuditBench extends Rates {
  n: number;
  sensors?: Record<string, number>;
  shown?: Record<string, number>;
  methods?: { rules: Rates; forest: Rates; both: Rates };
  not_enough_data?: string;
  as_of?: string;
  stations?: Record<string, string>;
  ambient?: { hours: number; real: number; filled: number; synthetic: number };
  nodes?: string[];
}

const METHODS = [["rules", "Rule checks"], ["forest", "Isolation Forest"], ["both", "Either"]] as const;
const FAULTS = ["flatline", "dropout", "too_clean", "drift", "rh_bias"];

const pct = (x: number | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function benchmarkTable(a: AuditBench | undefined) {
  if (!a || !a.n) return null;
  const methods = a.methods
    ? METHODS.map(([key, label]) => ({ key, label, ...a.methods![key] }))
    : [{ key: "rules", label: "Rule checks", precision: a.precision, recall: a.recall, detected: a.detected }];
  const seen = FAULTS.filter((f) => methods.some((m) => m.detected?.[f] != null));
  return {
    methods: methods.map(({ key, label }) => ({ key, label })),
    faults: seen.map((f) => ({
      fault: f, label: sentence(FAULT_LABEL[f] ?? f), sensors: a.sensors?.[f] ?? null, shown: a.shown?.[f] ?? null,
      rates: methods.map((m) => pct(m.detected?.[f])),
    })),
    healthy: { sensors: a.sensors?.none ?? null, rates: methods.map((m) => pct(m.detected?.none)) },
    precision: methods.map((m) => pct(m.precision)),
    recall: methods.map((m) => pct(m.recall)),
  };
}

// Where the simulated sensors' air came from: the stations they were built on and how much of the
// scored week those stations measured. Hours a station missed come from the next station that
// measured them, never from a model fill.
export function ambientNote(a: AuditBench): string {
  const names = Object.values(a.stations ?? {}).join(", ");
  const s = a.ambient;
  if (!s || !names) return "Simulated sensors built from station readings.";
  if (s.real === 0) return `Simulated sensors built from synthetic readings at ${names}.`;
  if (s.real === 1) return `Simulated sensors built from real readings at ${names}: all of the scored week measured.`;
  const rest = [
    s.filled > 0 ? "each hour a station missed comes from the next station that measured it" : null,
    s.synthetic > 0 ? `${pct(s.synthetic)} synthetic` : null,
  ].filter(Boolean).join("; ");
  return `Simulated sensors built from real readings at ${names}: ${pct(s.real)} of the scored week measured${rest ? `; ${rest}` : ""}.`;
}

// The calibration date the audit used, kept with the run. A date, so it's shown as stored, with no time zone shift.
export function calibrationNote(a: { calibrated_on: string | null; simulated: boolean }): string {
  if (!a.calibrated_on) return "No calibration date on record.";
  const d = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" })
    .format(new Date(`${a.calibrated_on}T00:00:00Z`));
  return `Last calibrated on ${d}${a.simulated ? " (simulated date)" : ""}.`;
}
