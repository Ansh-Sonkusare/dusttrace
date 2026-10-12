// The pilot wards (PRD Round 2). Shared by the proxy (which reads ?ward= and the cookie) and the
// queries (which read the header the proxy sets). Pure, so it's unit-tested.

export const WARDS = [
  { id: "K-East", name: "K-East (Andheri East)" },
  { id: "P-North", name: "P-North (Malad)" },
] as const;
export type WardId = (typeof WARDS)[number]["id"];
export const DEFAULT_WARD: WardId = "K-East";
export const WARD_COOKIE = "dt_ward";
export const WARD_HEADER = "x-dusttrace-ward";

const known = (w: string | null | undefined): w is WardId => WARDS.some((x) => x.id === w);

export function pickWard(query: string | null | undefined, cookie: string | null | undefined, fallback?: string): WardId {
  if (known(query)) return query;
  if (known(cookie)) return cookie;
  return known(fallback) ? fallback : DEFAULT_WARD;
}
