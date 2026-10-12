// Console password (HTTP Basic). Ward data is sensitive, so the console sits behind DUSTTRACE_PASSWORD.
// Resident pages (/s/…), site-manager plans (/plan/…, which carry their own signed token) and the
// public report endpoint stay open.

const PUBLIC = [/^\/s\//, /^\/plan\//, /^\/api\/report$/, /^\/_next\//, /^\/maplibre\//, /^\/favicon\.ico$/];

export type AuthResult = "ok" | "challenge" | "misconfigured";

export function isPublicPath(path: string): boolean {
  return PUBLIC.some((re) => re.test(path));
}

function sameText(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function passwordFrom(header: string | null): string | null {
  if (!header?.startsWith("Basic ")) return null;
  try {
    const decoded = atob(header.slice(6));
    const i = decoded.indexOf(":");
    return i < 0 ? null : decoded.slice(i + 1);
  } catch {
    return null;
  }
}

export function checkAuth(path: string, header: string | null, password: string | undefined, production: boolean): AuthResult {
  if (isPublicPath(path)) return "ok";
  if (!password) return production ? "misconfigured" : "ok";
  const given = passwordFrom(header);
  return given !== null && sameText(given, password) ? "ok" : "challenge";
}
