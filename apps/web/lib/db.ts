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

export const WARD = process.env.DUSTTRACE_WARD ?? "K-East";
