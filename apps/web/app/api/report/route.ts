import { NextResponse, type NextRequest } from "next/server";
import { q } from "@/lib/db";
import { countReports, getSite, wardAt } from "@/lib/queries";
import { cleanJpeg, PHOTO_MAX_BYTES, type Jpeg } from "@/lib/photo";
import { hashIp, parseReport, rateLimit, REPORT_ERROR, reportPage } from "@/lib/report";

const MAX_BODY = PHOTO_MAX_BYTES + 64 * 1024; // the photo plus a few short fields

// Public: residents post a report from /s/[id] or, for a place with no site, from /report-dust. Validated,
// rate-limited per device, stored as 'new'. The pages post with fetch and get JSON back (201, or 400/429
// with a message), as does any other client; a plain form post without JavaScript (a browser navigation)
// is sent back to its page with ?r=<code>, which the page shows as a message.
export async function POST(request: NextRequest) {
  const navigate = request.headers.get("sec-fetch-mode") === "navigate";
  let siteId: string | null = null;
  const reply = (r: string, status: number, body: Record<string, unknown>) => navigate
    ? NextResponse.redirect(new URL(`${reportPage(request.headers.get("referer"), siteId)}?r=${r}`, request.url), 303)
    : NextResponse.json(body, { status });
  const refuse = (error: string, status = 400) => reply(error, status, { error, message: REPORT_ERROR[error] });
  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY) return refuse("too_big");
  const form = await request.formData().catch(() => null);
  if (!form) return refuse("rejected");
  siteId = String(form.get("site_id") ?? "").trim() || null;
  const parsed = parseReport(form);
  if (!parsed.ok) return refuse(parsed.error);
  const r = parsed.value;

  const site = r.site_id ? await getSite(r.site_id) : null;
  if (r.site_id && !site) return refuse("site");
  const wardId = site ? site.ward_id : await wardAt(r.lat!, r.lon!);
  if (!wardId) return refuse("outside");

  const file = form.get("photo");
  let photo: Jpeg | null = null;
  if (file instanceof File && file.size > 0) {
    const checked = cleanJpeg(new Uint8Array(await file.arrayBuffer()));
    if (!checked.ok) return refuse(checked.error);
    photo = checked.value;
  }

  const ip = (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  const ipHash = hashIp(ip, process.env.REPORT_SALT ?? "dusttrace-reports");
  if (rateLimit(await countReports(ipHash, r.site_id)) !== "ok") return refuse("too_many", 429);

  const [row] = await q<{ id: string }>(
    `with r as (insert into citizen_reports (site_id, ward_id, kind, note, lat, lon, accuracy_m, ip_hash)
                values ($1, $2, $3, nullif($4, ''), $5, $6, $7, $8) returning id),
          p as (insert into report_photos (report_id, jpeg, width, height)
                select id, $9, $10, $11 from r where $9::bytea is not null)
     select id from r`,
    [r.site_id, wardId, r.kind, r.note, r.lat, r.lon, r.accuracy_m, ipHash,
     photo ? Buffer.from(photo.bytes) : null, photo?.width ?? null, photo?.height ?? null]);

  return reply("sent", 201, { id: Number(row.id), photo: photo !== null });
}
