import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getLatestRun, getSites, getWindows } from "@/lib/queries";
import { publicWindows } from "@/lib/publicApi";
import { guard, ok } from "@/lib/publicGuard";

export const dynamic = "force-dynamic";

/** Safe-Work Windows per site and hour for the latest run (go, caution, avoid). */
export async function GET(request: NextRequest) {
  const limited = await guard(request);
  if (limited) return limited;
  const run = await getLatestRun();
  if (!run) return NextResponse.json({ error: "No forecast yet." }, { status: 404 });
  const [rows, sites] = await Promise.all([getWindows(run.id), getSites()]);
  return ok({ run_id: run.id, issued_at: run.issued_at, data_mode: run.data_mode, sites: publicWindows(rows, sites) });
}
