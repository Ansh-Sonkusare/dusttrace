import QRCode from "qrcode";
import { type NextRequest } from "next/server";
import { getSite } from "@/lib/queries";

// QR code for the site's LED board, pointing at its public page. Behind the console password.
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!(await getSite(id))) return new Response("Unknown site", { status: 404 });
  const base = process.env.PUBLIC_BASE_URL ?? request.nextUrl.origin;
  const svg = await QRCode.toString(`${base}/s/${encodeURIComponent(id)}`, { type: "svg", margin: 2, errorCorrectionLevel: "M" });
  return new Response(svg, {
    headers: { "Content-Type": "image/svg+xml", "Content-Disposition": `inline; filename="dusttrace-site-${id}.svg"` },
  });
}
