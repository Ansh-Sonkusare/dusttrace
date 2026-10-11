import { NextResponse } from "next/server";
import { getLatestRun, getWardForecast, getWindows } from "@/lib/queries";

export const dynamic = "force-dynamic";

/** Latest run as JSON: forecast and Safe-Work Windows. Used by the future site-manager app. */
export async function GET() {
  const run = await getLatestRun();
  if (!run) return NextResponse.json({ run: null }, { status: 404 });
  const [forecast, windows] = await Promise.all([getWardForecast(run.id), getWindows(run.id)]);
  return NextResponse.json({ run, forecast, windows });
}
