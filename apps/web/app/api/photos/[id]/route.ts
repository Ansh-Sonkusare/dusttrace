import { type NextRequest } from "next/server";
import { checkAuth } from "@/lib/auth";
import { getPhoto } from "@/lib/queries";

// A resident's photo for the officer reviewing it. Photos may show people, so this sits behind the console
// password (checked by proxy.ts and again here) and is never cached by a shared cache.
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = checkAuth(request.nextUrl.pathname, request.headers.get("authorization"),
    process.env.DUSTTRACE_PASSWORD, process.env.NODE_ENV === "production");
  if (auth === "misconfigured") return new Response("Set DUSTTRACE_PASSWORD to open the ward console.", { status: 503 });
  if (auth === "challenge") {
    return new Response("Ward console: enter the password.", {
      status: 401, headers: { "WWW-Authenticate": 'Basic realm="DustTrace ward console", charset="UTF-8"' } });
  }
  const { id } = await params;
  const jpeg = /^\d{1,15}$/.test(id) ? await getPhoto(id) : null;
  if (!jpeg) return new Response("No photo", { status: 404 });
  return new Response(new Uint8Array(jpeg), {
    headers: { "Content-Type": "image/jpeg", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": `inline; filename="report-${id}.jpg"` },
  });
}
