import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getDustScores, getLatestRun, getSites } from "@/lib/queries";
import { publicScores } from "@/lib/publicApi";
import { guard, ok } from "@/lib/publicGuard";

export const dynamic = "force-dynamic";

/** Each site's Dust Score (0-100) and band from the latest run. */
export async function GET(request: NextRequest) {
  const limited = await guard(request);
  if (limited) return limited;
  const run = await getLatestRun();
  if (!run) return NextResponse.json({ error: "No forecast yet." }, { status: 404 });
  const [scores, sites] = await Promise.all([getDustScores(run.id), getSites()]);
  const by = new Map(sites.map((s) => [s.id, s]));
  const rows = scores.filter((s) => by.has(s.site_id)).map((s) => ({ ...s, name: by.get(s.site_id)!.name, demo: by.get(s.site_id)!.demo }));
  return ok({ run_id: run.id, issued_at: run.issued_at, sites: publicScores(rows) });
}
