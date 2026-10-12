# DustTrace: notes for Claude

Start with `HANDOFF.md` (context, status, next steps) and `docs/design-system.md` (every visual decision).

## Layout
- `services/engine`: Python package `dusttrace` (ingest, LightGBM forecast, Gaussian plume, Safe-Work Windows). CLI: `python -m dusttrace <cmd>`.
- `apps/web`: Next.js 16 App Router console (React 19, TypeScript 5, `pg`, MapLibre). Server components query Postgres directly in `lib/queries.ts`.
- `supabase/migrations`: SQL schema (Postgres 16 + PostGIS). Add new numbered files; never edit applied ones. Every migration must be safe to re-run (the hourly job runs `init-db`), and every new table gets `enable row level security`.
- `data/seed/k-east.json`: ward, seed stations, demo sites and receptors (approximate positions, `demo: true`).
- `docs/`: PRD, pitch deck (PDF, PPTX, HTML source), prototype, video kit, screenshots.

## Commands
- Engine tests: `cd services/engine && pytest -q`. Database tests need `TEST_DATABASE_URL` (Postgres + PostGIS; the tests wipe it) and run in CI against a PostGIS service.
- Work is tracked as GitHub issues; write the test first, one PR per issue.
- Full local run: `python -m dusttrace all` (needs `DATABASE_URL`; default `postgresql://postgres@localhost:5432/dusttrace`)
- Web: `cd apps/web && npm run typecheck && npm test && npm run build`; dev server `npm run dev`. Unit tests (Vitest) cover the pure logic in `lib/`; keep server code thin around it.
- The console sits behind `DUSTTRACE_PASSWORD` (HTTP Basic, `proxy.ts`); without it, production returns 503. `/s/…`, `/plan/…` and `/api/report` stay public.
- `predev`/`prebuild` copy the MapLibre worker into `public/maplibre/` (MapLibre can't find its worker under the Next bundler). Don't remove it.

## Conventions
- Times are stored in UTC and shown in IST (`lib/format.ts`). Write `µg/m³`.
- Any synthetic or demo data must stay visibly labelled (`synthetic` columns, `data_mode`, `demo` flags, the console banner).
- UI copy is sentence case and plain-spoken, with no all-caps labels. The accent is amber `#E0A245`; status colours are reserved; never blue.
- Pages use `export const dynamic = "force-dynamic"` and show an empty state when no run exists.
- Keep `globals.css` tokens and `docs/design-system.md` in sync.
- Team credit is "Team ARA IGNITE: Ansh, Dhruv, Anuj, Sarang". No institution name.
