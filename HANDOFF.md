# DustTrace handoff

Read this first in any new Claude Code session. It replaces the original chat, which covered the pitch, design work and the first MVP build.

## The project

- **Who:** Team ARA IGNITE: Ansh Sonkusare (Teak, repo owner), Dhruv, Anuj, Sarang. Don't show an institution name on any material.
- **What for:** Techfest IIT Bombay **InnovateX 2026–27**, Theme 2 "Rising AQI".
- **Dates:** Round 1 pitch submitted. **Round 2 report is due Dec 1, 2026**, and the finals run Dec 15–18, 2026.
- **The idea:** DustTrace prevents construction dust in Mumbai. It forecasts PM10 48 h ahead, models where each site's dust plume will drift, and gives every site **Safe-Work Windows**: hours to *avoid*, take *caution* with, or *go* ahead with dusty work. Enforcement officers get ranked cases that an agent builds, and residents see a public Dust Score through a QR code on the site hoarding. It is built on sensors Mumbai already has: CAAQMS stations and BMC's mandated site sensors. Low-cost DustTrace Nodes and BEST-bus sensors come later.
- **One-liner:** "We stop construction dust before it reaches people: forecast spikes 48 h ahead, move dusty work to safer hours, and point BMC at the sites to inspect."
- **Pilot ward:** K-East (Andheri East). Bounding box `[72.835, 19.090, 72.910, 19.140]`.

Full product spec: `docs/product/PRD.md` (also as a PDF).

## What exists

| Thing | Where | Status |
|---|---|---|
| PRD | `docs/product/PRD.md`, `PRD.pdf` | Done (Round 1) |
| Pitch deck | `docs/pitch/DustTrace-Round1-Pitch.pdf` and `.pptx`; HTML source in `docs/pitch/deck-source/` | 23 slides: 16 pitch + 7 backups, about 8:10 spoken |
| Speaker script | `docs/pitch/DustTrace-pitch-script.txt` | Notes for each slide |
| Clickable prototype | `docs/prototype/dusttrace-console.html` | Single file with demo data; the source for all video screens |
| 30 s teaser | `docs/video/DustTrace-30s-teaser.mp4` (+ `-silent`) | Done |
| 2-min film plan | `docs/video/storyboard.md` and `keyframes/`, `screens/`, `detail/`, `phone/` | Planned, not rendered |
| Design system | `docs/design-system.md` | Source of truth for every visual |
| **MVP engine** | `services/engine` (Python) | Working end to end; 10 tests pass |
| **MVP console** | `apps/web` (Next.js) | Overview, Forecast, Sites, Site detail, `/api/run` |
| DB schema | `supabase/migrations/` (`0001_init`, `0002_lock_rest_api`) | Postgres + PostGIS; tables closed to Supabase's REST API |
| **Supabase project** | `dusttrace`, ref `utcdxirkqpvtwndswfyn`, ap-south-1, free plan | Schema and seed loaded; no readings or runs yet |
| CI + hourly job | `.github/workflows/` | CI on push; the hourly job waits for the `DATABASE_URL` secret |

Claude artifacts from the original chat (they belong to Ansh's account and can be opened in claude.ai):
- Slides: https://claude.ai/artifact/2SQyeRzm3zWYZC8Ko7v8yX. The viewer reads `project/deck.json` and `project/slides/*.html` only.
- Prototype console: https://claude.ai/artifact/N4mmYuVv6LV76Sht2ze2Yv
- PRD doc: https://claude.ai/artifact/Jh38Mnw8yP7u5tFdvW6Hi9
- Video storyboard doc: https://claude.ai/artifact/LyG166AXoX9ShLULnyx4qW

## MVP scope (the "real-data core")

Chosen stack: **Next.js + Supabase (Postgres/PostGIS) + Python**. Scope: station and weather ingest, a 48 h PM10 forecast, a plume map and Safe-Work Windows for K-East.

```
Open-Meteo (weather, BLH) ─┐
OpenAQ v3 (CPCB stations) ─┼─> engine ingest ─> Postgres ─> engine run ─> forecasts, plumes, safe_windows ─> Next.js console
Overpass (schools, hosp.) ─┘                                (LightGBM + Gaussian plume)
```

### Engine (`services/engine/dusttrace`)

- `sources/`: Open-Meteo forecast and archive, OpenAQ v3 (needs `OPENAQ_API_KEY`), Overpass, plus `synthetic.py` fallbacks.
- `forecast.py`: direct multi-horizon **LightGBM**.
  - Features: lags 1/2/3/6/12/24, 24 h mean and max, horizon, IST hour, day of week, month, station, weather at the target hour, and ventilation (wind × BLH).
  - Models: a median model, 10%/90% quantile models, and an exceedance classifier (PM10 > 100).
  - Evaluation: time-ordered holdout (last 20%) against persistence. The ward value is the mean across stations.
- `plume.py`: Gaussian plume.
  - Briggs urban σ by Pasquill class, chosen from wind speed and IST daylight.
  - Hourly meander widening, and uniform mixing once σz ≥ 1.6 × BLH.
  - Virtual source set back by √area.
  - AP-42 emission rate of 8.6e-5 g/s/m² × an activity factor: demolition 3, excavation 2, debris 1.5, structure 1.
  - The footprint is traced from 50 m out at 25 µg/m³.
- `windows.py`:
  - **Avoid** if a school or hospital gets ≥ 40 µg/m³ added, or any receptor gets ≥ 40 while P(PM10 > 100) ≥ 0.6.
  - **Caution** if any receptor gets ≥ 15, or P ≥ 0.6.
  - Otherwise **Go**.
  - Each hour carries a plain reason naming the receptor and the wind.
- `pipeline.py` / `cli.py`: `python -m dusttrace init-db | seed | osm | ingest [--mode auto|live|synthetic] [--days N] | run | all`.

### Live vs synthetic (important)

The build sandbox could not reach Open-Meteo, OpenAQ or Overpass, so **the live code paths are written and parser-tested against fixtures but have never run against the real APIs**.
- In `--mode auto`, a failing source falls back to synthetic data. Those rows are flagged `synthetic=true`, and the run's `data_mode` becomes `synthetic` or `mixed`.
- The console shows an amber banner and pill whenever the data isn't live.
- Seed stations, the six sites (A–F) and the ten receptors in `data/seed/k-east.json` are **approximate demo positions**. Replace the stations with the real OpenAQ locations; `ingest` does this automatically when it finds them in the bbox. Replace the receptors with `dusttrace osm`.

Latest synthetic run (420 days of history):
- Mean error: 3.5 µg/m³ vs 8.9 for persistence.
- Exceedance F1: 0.69 vs 0.14.
- 10–90% coverage: 73% (target 80%).
- Windows over the 48 h: Go 221, Caution 48, Avoid 19 hours. The avoid hours fall in calm mornings and evenings, when Site A's plume reaches the school west of Metro 7A.

## Run it locally

```bash
# 1. Database: Postgres 16 + PostGIS (or a Supabase project)
export DATABASE_URL=postgresql://postgres@localhost:5432/dusttrace

# 2. Engine
cd services/engine
pip install -e ".[dev]"
pytest -q                         # 10 tests, ~25 s
python -m dusttrace all           # migrate, seed, ingest (auto, 420 days), run
# later runs: python -m dusttrace ingest --days 3 && python -m dusttrace run

# 3. Console
cd ../../apps/web
cp .env.example .env.local        # set DATABASE_URL
npm install
npm run dev                       # http://localhost:3000
```

Use at least 420 days of history. With 120 days the holdout crosses a season change and the model loses to persistence.

## Next milestones (suggested order)

1. **Supabase project:** done. The project `dusttrace` (ref `utcdxirkqpvtwndswfyn`, Mumbai) has both migrations and the K-East seed applied. Still to do, by a person:
   - Set the database password (Project Settings > Database > Reset database password). It was never shown when the project was created.
   - Copy the **Session pooler** URI from the dashboard's Connect button. GitHub runners have no IPv6, so the direct `db.<ref>.supabase.co` host won't work from Actions.
   - Add the repo secrets `DATABASE_URL` (that URI) and `OPENAQ_API_KEY`.
   - Trigger the "Hourly forecast" workflow once by hand with `days=420` to backfill. From then on it runs at :17 every hour.
   - The workflow only runs `ingest` and `run`. Apply any new migration with `python -m dusttrace init-db` (all migrations are safe to re-run) or the Supabase MCP, and give every new table `enable row level security`.
2. **Verify live data:** check the run's `data_mode` is `live`, the stations are real CPCB sites in or near K-East, and `dusttrace osm` loads real schools and hospitals. Fix any parser drift.
3. **Deploy the console** on Vercel, root `apps/web`, env `DATABASE_URL`. Add a basic password, because ward data is sensitive.
4. **Calibrate:** compare plume increments with station deltas downwind of real sites, tune the emission factors, and reach about 80% coverage for the quantile band.
5. **Agent cases (PRD D1–D10):** the inspection case builder ranks sites, checks the sensor, satellite and bus evidence, proposes actions, and needs an officer's sign-off.
6. **Site-manager view:** a mobile web page that takes tomorrow's windows from `/api/run`, with an "Accept plan" button.
7. **Resident QR page:** a public Dust Score for each site, plus a report form.
8. **Round 2 report (Dec 1):** use real metrics from step 2, screenshots from `docs/screens/`, and the plume method above. Keep the "demo" and "simulated pilot" labels honest.

## Decisions worth keeping

- PM10 is the primary metric. Construction dust is coarse, and India's 24 h PM10 standard is 100 µg/m³.
- The Safe-Work thresholds are *modelled increments* at receptors, not ambient totals. That way a site is judged on its own contribution.
- Times are stored in UTC and shown in IST. Night hours (22:00–06:00) are dimmed because dusty work is not allowed then.
- Every number on screen that is synthetic or demo is labelled as such.
- Design: dark graphite with amber as the only accent and Manrope only; never blue. See `docs/design-system.md`.
