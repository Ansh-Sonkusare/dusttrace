const TZ = "Asia/Kolkata";

export function hhmm(ts: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(ts));
}

export function dayShort(ts: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" }).format(new Date(ts));
}

export function dayHour(ts: string): string {
  return `${new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short" }).format(new Date(ts))} ${hhmm(ts)}`;
}

export function istHour(ts: string): number {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", hour12: false }).format(new Date(ts))) % 24;
}

export const STATUS_LABEL = { go: "Go", caution: "Caution", avoid: "Avoid" } as const;

export const ACTIVITY_LABEL: Record<string, string> = {
  demolition: "Demolition",
  excavation: "Excavation",
  structure: "Structure work",
  debris: "Debris handling",
};

export const TRUST_LABEL = { trusted: "Trusted", check: "Check", untrusted: "Untrusted" } as const;
export const TRUST_TONE = { trusted: "go", check: "caution", untrusted: "avoid" } as const;

// What the simulator injected, in an officer's words.
export const FAULT_LABEL: Record<string, string> = {
  none: "no fault",
  flatline: "stuck readings",
  dropout: "switched off during work",
  too_clean: "placed out of the dust",
  drift: "calibration drift",
  rh_bias: "humidity over-reading",
};
