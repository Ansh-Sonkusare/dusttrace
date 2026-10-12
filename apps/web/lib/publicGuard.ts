import { NextResponse, type NextRequest } from "next/server";
import { q } from "./db";
import { apiRateLimit } from "./publicApi";
import { hashIp } from "./report";

const HEADERS = {
  "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600", // served from the edge for 5 min
  "Access-Control-Allow-Origin": "*",
};

// Count this request against the caller's hourly limit; returns a 429 response when over it.
export async function guard(request: NextRequest): Promise<NextResponse | null> {
  const ip = (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  const ipHash = hashIp(ip, process.env.REPORT_SALT ?? "dusttrace-reports");
  const [{ n }] = await q<{ n: number }>(
    "select count(*)::int as n from api_requests where ip_hash=$1 and at > now() - interval '1 hour'", [ipHash]);
  if (apiRateLimit(n) === "too_many") {
    return NextResponse.json({ error: "Too many requests; try again within the hour." }, { status: 429, headers: { "Retry-After": "3600" } });
  }
  await q("insert into api_requests (ip_hash, path) values ($1, $2)", [ipHash, request.nextUrl.pathname]);
  await q("delete from api_requests where at < now() - interval '1 day'");
  return null;
}

export const ok = (body: unknown) => NextResponse.json(body, { headers: HEADERS });
