import { type NextRequest } from "next/server";
import { getPhoto } from "@/lib/queries";

// A resident's photo for the officer reviewing it. Photos may show people, so this sits behind the console
// password (proxy.ts) and is never cached by a shared cache.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const jpeg = /^\d{1,15}$/.test(id) ? await getPhoto(id) : null;
  if (!jpeg) return new Response("No photo", { status: 404 });
  return new Response(new Uint8Array(jpeg), {
    headers: { "Content-Type": "image/jpeg", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": `inline; filename="report-${id}.jpg"` },
  });
}
