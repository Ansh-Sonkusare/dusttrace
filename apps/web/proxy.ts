import { NextResponse, type NextRequest } from "next/server";
import { checkAuth } from "./lib/auth";

export function proxy(request: NextRequest) {
  const result = checkAuth(request.nextUrl.pathname, request.headers.get("authorization"),
    process.env.DUSTTRACE_PASSWORD, process.env.NODE_ENV === "production");
  if (result === "ok") return NextResponse.next();
  if (result === "misconfigured") {
    return new NextResponse("Set DUSTTRACE_PASSWORD to open the ward console.", { status: 503 });
  }
  return new NextResponse("Ward console: enter the password.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="DustTrace ward console", charset="UTF-8"' },
  });
}
