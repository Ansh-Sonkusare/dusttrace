"use server";

import { revalidatePath } from "next/cache";
import { q } from "./db";
import { parseOutcome } from "./officer";
import { planSecret, verifySite } from "./plan";
import { getReportedPlaces } from "./queries";
import { parseReview } from "./report";
import { candidateSite, parseCandidateVerdict, placeSite } from "./sites";

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

// An officer verifies or rejects a resident's report. On the next run a verified report counts toward its
// site's Dust Score, and a rejected one stops counting toward the inspection priority.
export async function reviewReport(form: FormData): Promise<void> {
  const parsed = parseReview(form);
  if (!parsed.ok) return;
  await q("update citizen_reports set status=$2, reviewed_at=now() where id=$1 and status='new'", [parsed.value.id, parsed.value.verdict]);
  revalidatePath("/resident-reports");
  revalidatePath("/inspect");
}

// An officer confirms a place residents reported (F2) into a real site, as with a satellite candidate, or
// rejects it. The page posts one of the place's reports; the place is grouped again from the reports as they
// stand, so one that arrived after the page loaded goes with it. Confirming moves its reports to the new site;
// rejecting rejects only the reports nobody has checked yet.
export async function decidePlace(form: FormData): Promise<void> {
  const parsed = parseCandidateVerdict(form);
  if (!parsed.ok) return;
  const { id, verdict } = parsed.value;
  const [r] = await q<{ ward_id: string }>("select ward_id from citizen_reports where id=$1 and site_id is null", [id]);
  const place = r && (await getReportedPlaces(r.ward_id)).find((p) => p.ids.includes(id));
  if (!place) return;
  if (verdict === "confirmed") {
    const s = placeSite(place);
    await q(
      `insert into sites (id, name, activity, lat, lon, ward_id, sensor_status, demo, source)
       values ($1, $2, $3, $4, $5, $6, 'not_connected', false, 'citizen') on conflict (id) do nothing`,
      [s.id, s.name, s.activity, s.lat, s.lon, r.ward_id],
    );
    await q("update citizen_reports set site_id=$2 where id = any($1) and site_id is null", [place.ids, s.id]);
  } else {
    await q("update citizen_reports set status='rejected', reviewed_at=now() where id = any($1) and site_id is null and status='new'",
      [place.ids]);
  }
  revalidatePath("/inspect");
  revalidatePath("/sites");
  revalidatePath("/resident-reports");
}
