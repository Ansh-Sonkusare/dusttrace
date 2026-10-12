import { NextResponse, type NextRequest } from "next/server";
import { q } from "@/lib/db";
import { countReports, getSite } from "@/lib/queries";
import { hashIp, parseReport, rateLimit } from "@/lib/report";

// Public: residents post the report form from /s/[id]. Validated, rate-limited per device, stored as 'new'.
export async function POST(request: NextRequest) {
  const form = await request.formData();
  const parsed = parseReport(form);
  const siteId = String(form.get("site_id") ?? "");
  const back = (r: string) => NextResponse.redirect(new URL(`/s/${encodeURIComponent(siteId)}?r=${r}`, request.url), 303);
  if (!parsed.ok || !(await getSite(parsed.value.site_id))) return back("invalid");

  const ip = (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  const ipHash = hashIp(ip, process.env.REPORT_SALT ?? "dusttrace-reports");
  if (rateLimit(await countReports(ipHash, parsed.value.site_id)) !== "ok") return back("too_many");

  await q("insert into citizen_reports (site_id, kind, note, ip_hash) values ($1, $2, nullif($3, ''), $4)",
    [parsed.value.site_id, parsed.value.kind, parsed.value.note, ipHash]);
  return back("sent");
}
