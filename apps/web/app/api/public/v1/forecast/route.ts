import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getForecastDays, getLatestRun, getWard, getWardForecast } from "@/lib/queries";
import { publicForecast } from "@/lib/publicApi";
import { guard, ok } from "@/lib/publicGuard";

export const dynamic = "force-dynamic";

/** The latest 72 h ward PM10 forecast and its daily 24 h mean exceedance, with its data mode and sources. */
export async function GET(request: NextRequest) {
  const limited = await guard(request);
  if (limited) return limited;
  const [ward, run] = await Promise.all([getWard(), getLatestRun()]);
  if (!ward || !run) return NextResponse.json({ error: "No forecast yet." }, { status: 404 });
  const [hours, days] = await Promise.all([getWardForecast(run.id), getForecastDays(run.id)]);
  return ok(publicForecast(run, hours, ward.name, days));
}
