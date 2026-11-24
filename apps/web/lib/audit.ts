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
  stations?: Record<string, StationHours>;
  synthetic_ambient?: boolean;
  nodes?: string[];
}
// A station the simulated sensors were built on, and where its sensors' ambient came from each hour.
interface StationHours { name: string; sensors: number; hours: number; measured: number; next_station: number; interpolated: number }

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

// Where the simulated sensors' air came from: the stations they were built on and, hour by hour, whether
// that station measured it, the next station that measured it stood in, or no station did.
export function ambientNote(a: AuditBench): string {
  const st = Object.values(a.stations ?? {});
  if (!st.length || typeof st[0] !== "object") return "Simulated sensors built from station readings.";
  const names = st.map((x) => x.name).join(", ");
  if (a.synthetic_ambient) return `All ${a.n} simulated sensors are built from synthetic readings at ${names}.`;
  if (st.length > 1) {
    return `The ${a.n} simulated sensors are built on ${st.length} stations: ${st.map((x) => `${x.name} (${x.sensors} sensors, ${x.measured} of ${x.hours} hours measured)`).join(", ")}.`;
  }
  const [x] = st;
  if (x.measured === x.hours) return `All ${a.n} simulated sensors share one station, ${x.name}, which measured all ${x.hours} hours of the scored week.`;
  const rest = [
    x.next_station > 0 ? `the other ${x.next_station} came from the next station that measured them` : null,
    x.interpolated > 0 ? `${x.interpolated} that no station measured were interpolated` : null,
  ].filter(Boolean).join("; ");
  return `All ${a.n} simulated sensors share one station, ${x.name}, which measured ${x.measured} of the scored week's ${x.hours} hours; ${rest}.`;
}

// The calibration date the audit used, kept with the run. A date, so it's shown as stored, with no time zone shift.
export function calibrationNote(a: { calibrated_on: string | null; simulated: boolean }): string {
  if (!a.calibrated_on) return "No calibration date on record.";
  const d = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" })
    .format(new Date(`${a.calibrated_on}T00:00:00Z`));
  return `Last calibrated on ${d}${a.simulated ? " (simulated date)" : ""}.`;
}
