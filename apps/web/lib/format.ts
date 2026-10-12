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

export const ROUTE_LABEL = { auto: "Automatic", site: "Site manager", L1: "Ward officer", L2: "Assistant Commissioner" } as const;

export const STATE_LABEL: Record<string, string> = {
  APPROVAL_ROUTING: "Waiting for approval",
  AWAITING_EVIDENCE: "Waiting for evidence",
  VERIFYING: "Checking the air",
  DONE: "Closed",
};

export const ACTION_LABEL: Record<string, string> = {
  ISSUE_SAFE_WORK_WINDOW: "Send Safe-Work Windows",
  SCHEDULE_MIST: "Schedule misting",
  PRE_WET_SITE: "Pre-wet the site",
  ALERT_RECEPTOR: "Alert the school or hospital",
  NOTIFY_RESIDENTS: "Notify residents",
  TRIGGER_MIST_NOW: "Mist now",
  PAUSE_DUSTY_TASK: "Pause dusty work",
  REQUEST_SITE_PHOTO: "Ask the site for a photo",
  REQUEST_SPOT_CHECK: "Officer spot check",
  FLAG_SENSOR_FOR_AUDIT: "Flag the monitor for audit",
  ADD_TO_INSPECTION: "Add to inspection list",
  REGISTER_UNSENSORED_SITE: "Register the site",
  ISSUE_NOTICE: "Issue a notice",
  RECOMMEND_STOP_WORK: "Recommend stop-work",
  REFER_NON_CONSTRUCTION: "Refer to MPCB or BMC",
  UPDATE_DUST_SCORE: "Update the Dust Score",
};

export const CAUSE_LABEL: Record<string, string> = {
  dry_excavation: "dry excavation", demolition: "demolition", truck_trackout: "truck track-out",
  uncovered_debris: "uncovered debris", sensor_fault: "sensor fault", non_construction: "not construction",
  weather_only: "weather alone",
};

export const STATUS_WORD: Record<string, string> = {
  done: "Done (logged)", sent: "Sent to site", proposed: "Needs a decision", approved: "Approved",
  declined: "Declined", requested: "Requested", answered: "Answered", expired: "No reply",
};

export function caseId(id: number): string {
  return `DT-KE-${String(id).padStart(4, "0")}`;
}

export const SCORE_BAND = {
  good: { label: "Good", tone: "go", meaning: "Keeps its dust in check. Fewer routine inspections." },
  fair: { label: "Fair", tone: "caution", meaning: "Some dust problems. Room to improve." },
  poor: { label: "Poor", tone: "avoid", meaning: "Repeated dust problems. At the top of the inspection list." },
} as const;

export const SCORE_PART: Record<string, { label: string; max: number }> = {
  trust: { label: "Its own dust monitor can be trusted", max: 30 },
  spikes: { label: "Few dust spikes traced to it", max: 25 },
  windows: { label: "Follows its Safe-Work Windows", max: 20 },
  reports: { label: "Few verified complaints from residents", max: 15 },
  inspections: { label: "Clean inspection record", max: 10 },
};
