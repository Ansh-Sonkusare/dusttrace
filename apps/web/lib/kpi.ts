// Ward KPIs (PRD F11) as overview tiles. Pure, unit-tested.

export interface KpiRaw {
  spike_p_tomorrow: number | null; sites_holding: number; untrusted: number; decisions: number; new_reports: number;
}

const s = (n: number, one: string, many: string) => (n === 1 ? one : many);

export function kpiTiles(k: KpiRaw): { value: string; label: string }[] {
  const waiting = k.decisions + k.new_reports;
  return [
    { value: k.spike_p_tomorrow == null ? "–" : `${Math.round(k.spike_p_tomorrow * 100)}%`, label: "Chance of ward PM10 above 100 tomorrow" },
    { value: String(k.sites_holding), label: `${s(k.sites_holding, "Site holding", "Sites holding")} dusty work in the next 24 h` },
    { value: String(k.untrusted), label: `Site ${s(k.untrusted, "monitor", "monitors")} not trusted` },
    { value: String(waiting), label: `Waiting on you: ${k.decisions} ${s(k.decisions, "decision", "decisions")}, ${k.new_reports} new ${s(k.new_reports, "report", "reports")}` },
  ];
}
