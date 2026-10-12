import { NextResponse, type NextRequest } from "next/server";
import { checkAuth } from "./lib/auth";
import { WARD_COOKIE, WARD_HEADER, pickWard } from "./lib/wards";

export function proxy(request: NextRequest) {
  const result = checkAuth(request.nextUrl.pathname, request.headers.get("authorization"),
    process.env.DUSTTRACE_PASSWORD, process.env.NODE_ENV === "production");
  if (result === "misconfigured") {
    return new NextResponse("Set DUSTTRACE_PASSWORD to open the ward console.", { status: 503 });
  }
  if (result === "challenge") {
    return new NextResponse("Ward console: enter the password.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="DustTrace ward console", charset="UTF-8"' },
    });
  }
  // The ward: ?ward= switches it (and is remembered), else the cookie, else DUSTTRACE_WARD.
  const asked = request.nextUrl.searchParams.get("ward");
  // The public API is cached at the edge by URL, so there only ?ward= counts, never the cookie.
  const isApi = request.nextUrl.pathname.startsWith("/api/public/");
  const ward = pickWard(asked, isApi ? null : request.cookies.get(WARD_COOKIE)?.value, process.env.DUSTTRACE_WARD);
  const headers = new Headers(request.headers);
  headers.set(WARD_HEADER, ward);
  const res = NextResponse.next({ request: { headers } });
  if (!isApi && asked && asked === ward) res.cookies.set(WARD_COOKIE, ward, { path: "/", sameSite: "lax", maxAge: 60 * 60 * 24 * 180 });
  return res;
}
