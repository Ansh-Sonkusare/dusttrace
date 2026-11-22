import { NextResponse, type NextRequest } from "next/server";
import { q } from "@/lib/db";
import { keyMatches, parseNodePost } from "@/lib/node";

/**
 * DustTrace Node ingest. `Authorization: Bearer <node key>`, body
 * `{"node_id": "node-…", "readings": [{pm25, pm10, rh?, temp?, ts?}]}`.
 * Answers `{accepted, duplicate}`; 400 for a bad body, 401 for an unknown node or wrong key.
 */
export async function POST(request: NextRequest) {
  const parsed = parseNodePost(await request.json().catch(() => null), new Date());
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });
  const { nodeId, readings } = parsed.value;

  const key = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const [node] = await q<{ key_hash: string }>("select key_hash from nodes where id=$1 and active", [nodeId]);
  if (!node || !keyMatches(key, node.key_hash)) return NextResponse.json({ error: "Unknown node or key." }, { status: 401 });

  const rows = await q<{ n: number }>(
    `with ins as (
       insert into node_readings (node_id, ts, pm25_raw, pm10_raw, temp, rh, pm25_corrected, pm10_corrected)
       select $1, * from unnest($2::timestamptz[], $3::real[], $4::real[], $5::real[], $6::real[], $7::real[], $8::real[])
       on conflict (node_id, ts) do nothing returning 1)
     select count(*)::int as n from ins`,
    [nodeId, readings.map((r) => r.ts.toISOString()), readings.map((r) => r.pm25Raw), readings.map((r) => r.pm10Raw),
     readings.map((r) => r.temp), readings.map((r) => r.rh), readings.map((r) => r.pm25), readings.map((r) => r.pm10)],
  );
  await q("update nodes set last_seen_at = now() where id=$1", [nodeId]);
  const accepted = rows[0]?.n ?? 0;
  return NextResponse.json({ accepted, duplicate: readings.length - accepted });
}
