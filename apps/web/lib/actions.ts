"use server";

import { revalidatePath } from "next/cache";
import { q } from "./db";
import { parseOutcome } from "./officer";
import { planSecret, verifySite } from "./plan";
import { candidateSite, parseCandidateVerdict } from "./sites";

// An officer approves or declines an action the policy engine proposed (route L1 or L2).
// Only proposed actions can be decided; everything else the engine set stays as it is.
export async function decideAction(form: FormData): Promise<void> {
  const id = Number(form.get("id"));
  const verdict = String(form.get("verdict"));
  if (!Number.isInteger(id) || !["approved", "declined"].includes(verdict)) return;
  await q(
    `update case_actions set status=$2, decided_by='ward officer', decided_at=now()
      where id=$1 and status='proposed' and route in ('L1', 'L2')`,
    [id, verdict],
  );
  revalidatePath("/cases");
}

// An officer logs what they found at a site. It links to the site's open case and answers any spot
// check the agent asked for, so D7 won't escalate it. The engine reads outcomes on its next run.
export async function logOutcome(form: FormData): Promise<void> {
  const parsed = parseOutcome(form);
  if (!parsed.ok) return;
  const { site_id, outcome, note } = parsed.value;
  await q(
    `insert into inspections (site_id, case_id, outcome, note, officer)
     values ($1, (select id from cases where site_id=$1 and closed_at is null), $2, nullif($3, ''), 'ward officer')`,
    [site_id, outcome, note],
  );
  await q(
    `update case_actions set status='answered' where status='requested' and action='REQUEST_SPOT_CHECK'
        and case_id = (select id from cases where site_id=$1 and closed_at is null)`,
    [site_id],
  );
  revalidatePath("/officer");
  revalidatePath("/cases");
}

// A site manager accepts today's plan from their signed link. The token is checked again here.
export async function acceptPlan(form: FormData): Promise<void> {
  const siteId = String(form.get("site_id") ?? "");
  const token = String(form.get("t") ?? "");
  const secret = planSecret();
  if (!secret || !verifySite(siteId, token, secret)) return;
  await q(
    `insert into plan_acceptances (site_id, run_id, avoid_hours, accepted_by)
     select $1, r.id, (select count(*) from safe_windows w where w.run_id = r.id and w.site_id = $1 and w.status = 'avoid'
                                and w.ts <= r.issued_at + interval '24 hours'),
            'site manager'
       from latest_run r join sites s on s.ward_id = r.ward_id and s.id = $1`,
    [siteId],
  );
  revalidatePath(`/plan/${siteId}`);
}

// An officer confirms or rejects a satellite candidate (F2). A confirmed one becomes a real site
// (not demo) whose monitor feed isn't connected; the next engine run plans its Safe-Work Windows.
export async function decideCandidate(form: FormData): Promise<void> {
  const parsed = parseCandidateVerdict(form);
  if (!parsed.ok) return;
  const { id, verdict } = parsed.value;
  const rows = await q<{ id: number; ward_id: string; lat: number; lon: number; area_m2: number }>(
    "select id, ward_id, lat, lon, area_m2 from site_candidates where id=$1 and status='unverified' and site_id is null", [id]);
  const c = rows[0];
  if (!c) return;
  if (verdict === "confirmed") {
    const s = candidateSite(c);
    await q(
      `insert into sites (id, name, activity, lat, lon, ward_id, area_m2, sensor_status, demo, source)
       values ($1, $2, $3, $4, $5, $6, $7, 'not_connected', false, 'satellite') on conflict (id) do nothing`,
      [s.id, s.name, s.activity, s.lat, s.lon, c.ward_id, s.area_m2],
    );
    await q("update site_candidates set status='confirmed', site_id=$2 where id=$1", [id, s.id]);
  } else {
    await q("update site_candidates set status='rejected' where id=$1", [id]);
  }
  revalidatePath("/inspect");
  revalidatePath("/sites");
}
