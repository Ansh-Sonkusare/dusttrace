"use server";

import { revalidatePath } from "next/cache";
import { q } from "./db";

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
