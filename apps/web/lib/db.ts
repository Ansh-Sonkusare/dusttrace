import { WARD_HEADER, pickWard } from "./wards";
import { Pool } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var __dtPool: Pool | undefined;
}

export function pool(): Pool {
  if (!globalThis.__dtPool) {
    const url = process.env.DATABASE_URL ?? "postgresql://postgres@localhost:5432/dusttrace";
    globalThis.__dtPool = new Pool({
      connectionString: url,
      max: 5,
      ssl: /supabase\.(co|com)/.test(url) ? { rejectUnauthorized: false } : undefined,
    });
  }
  return globalThis.__dtPool;
}

export async function q<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const res = await pool().query(sql, params);
  return res.rows as T[];
}

// The ward this request is about: set by proxy.ts from ?ward=, the cookie or DUSTTRACE_WARD.
export async function ward(): Promise<string> {
  const { headers } = await import("next/headers");
  return pickWard((await headers()).get(WARD_HEADER), null, process.env.DUSTTRACE_WARD);
}
