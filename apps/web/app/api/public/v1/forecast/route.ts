import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getLatestRun, getWard, getWardForecast } from "@/lib/queries";
import { publicForecast } from "@/lib/publicApi";
import { guard, ok } from "@/lib/publicGuard";

export const dynamic = "force-dynamic";

/** The latest 48 h ward PM10 forecast, with its data mode and sources. */
export async function GET(request: NextRequest) {
  const limited = await guard(request);
  if (limited) return limited;
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return NextResponse.json({ error: "No forecast yet." }, { status: 404 });
  return ok(publicForecast(run, await getWardForecast(run.id), ward.name));
}
