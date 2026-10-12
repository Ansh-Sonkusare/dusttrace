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
| **Supabase project** | `dusttrace`, ref `utcdxirkqpvtwndswfyn`, ap-south-1, free plan | 420 days of live weather and real CPCB PM10 (11 stations, about 85k hours) loaded; runs anchored on synthetic samples while OpenAQ's CPCB feed is stale |
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
- `audit.py` (F1): site-sensor simulator and trust score.
  - Each site's sensor reads ambient + near-field dust while the site works + its plume when downwind. Faults are injected per `data/seed/k-east.json` (C too clean, E flatline, F dropout; D has no sensor).
  - Seven checks over 7 days (dropout, flatline, neighbour, working-hours signature, placement, humidity, drift) give a 0–100 score: trusted 70+, check 40–69, untrusted < 40 (D5).
  - Each run also scores a 50-sensor benchmark; its precision/recall are in `runs.metrics.audit`.
- `attribution.py` (F4): back-trajectories from each station through the next 24 forecast hours (weighted by P(PM10 > 100) ≥ 0.4) give each site an upwind score. Priority = 0.35·upwind + 0.25·(1 − trust) + 0.15·reports + 0.15·unsensored + 0.10·violations, in points out of 100, with the top two reasons. Stored in `inspection_rank`; shown on `/inspect`.
- `agent.py` (F12): the Dust Response Agent's policy engine. Each run builds a `SiteContext` per site and `decide` returns triggers, cause hypotheses, initial/final actions from the PRD catalog (each cites D1–D10 and a route: auto, site, L1, L2) and `what_changed`. Guards: D1 (no enforcement on one signal), D7 (unanswered requests escalate; nothing assumed), D9 (stop-work only proposed to L2). One open case per site in `cases`/`case_actions`; officer decisions and deadlines persist across runs. Console `/cases` approves or declines proposed actions. Alerts are logged, not sent.
- `dust_score.py` (F8): public 0–100 per site (trust 30, spikes 25, windows followed 20, verified reports 15, inspections 10; good 80+, poor < 40), stored in `dust_scores`. Residents open `/s/[id]` from the QR on the site board (`/api/qr/[id]`) and report dust via `/api/report` (validated, honeypot, rate-limited per salted IP hash; set `REPORT_SALT` and `PUBLIC_BASE_URL` in production). Reports count toward the priority score and the agent once not rejected, and toward the Dust Score once an officer verifies them.
- `alerts.py` (F11): per run, alerts with an action each: critical (spike, no relay, no accepted plan), action (site monitor hot inside an Avoid hour), receptor (school/hospital downwind in work hours), sensor (untrusted monitor). Stored in `alerts`; logged, not sent. The overview shows them with the F11 KPIs (spike risk tomorrow, sites holding, untrusted monitors, decisions and new reports waiting).
- `windows.py`:
  - **Avoid** if a school or hospital gets ≥ 40 µg/m³ added, or any receptor gets ≥ 40 while P(PM10 > 100) ≥ 0.6.
  - **Caution** if any receptor gets ≥ 15, or P ≥ 0.6.
  - Otherwise **Go**.
  - Each hour carries a plain reason naming the receptor and the wind.
- `pipeline.py` / `cli.py`: `python -m dusttrace init-db | seed | osm | ingest [--mode auto|live|synthetic] [--days N] | run | all`.

### Live vs synthetic (important)

First live runs (Oct 11, 2026, from GitHub Actions and the build sandbox):
- **Open-Meteo works.** The forecast and archive APIs both returned real weather from Actions. Both can time out or rate-limit (429), so requests retry (`sources/http.py`).
- **OpenAQ works, but its CPCB feed is stale.** It lists 12 PM stations that reported in the last 30 days around K-East, including Chakala-Andheri East (inside the ward), CSIA Airport T2, Kurla and Powai, with hourly history back to Aug 2025. Every CPCB station's newest reading is **2026-10-07 14:30 UTC**; only the US AirNow monitor (PM2.5 only) is current.
  - OpenAQ returns 500s for long ranges, so history is fetched in 30-day windows. The free key allows 60 requests a minute; a 420-day backfill takes about 6 minutes.
- **Freshness rule (`pipeline.anchor`, `FRESH_HOURS = 6`):** real stations anchor the forecast only while their newest reading is under 6 h old. Otherwise the seed stations' synthetic readings anchor it, so a stalled feed can't push the 48 h forecast into the past, and the run is `mixed`. The switch to real stations is automatic once OpenAQ catches up.
- The hourly job loads 3 days. After an outage longer than that, run the workflow by hand with more `days` to fill the gap.
- **Overpass works through a mirror** (overpass-api.de resets connections; `sources/overpass.py` falls back to kumi.systems and mail.ru). The bbox plus about 1 km gives about 230 schools and hospitals. Clinics, dental, diagnostic centres and unnamed "hospitals" are dropped, since OSM in Mumbai tags many of them `amenity=hospital`. A weekly workflow (`receptors.yml`) refreshes them.

How fallback works:
- In `--mode auto`, a failing source falls back to synthetic data. Those rows are flagged `synthetic=true`, and the run's `data_mode` becomes `synthetic` or `mixed`. Synthetic rows never overwrite real ones (guarded in `db.py`).
- The console shows an amber banner and pill whenever the data isn't live. The map and the observed line show only the stations the latest run used.
- Seed stations, the six sites (A–F) and the ten receptors in `data/seed/k-east.json` are **approximate demo positions**. Real OpenAQ stations are stored next to the seed ones and replace them in runs while fresh. Once OSM receptors exist, they replace the demo schools and hospitals in runs and on the map (`db.RECEPTORS_SQL`); the demo housing societies stay, labelled, until a real population source is added.

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
pytest -q                         # unit tests; database tests skip without TEST_DATABASE_URL
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/dusttrace_test pytest -q   # all tests (wipes that database)
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

1. **Supabase project:** done. The project `dusttrace` (ref `utcdxirkqpvtwndswfyn`, Mumbai) has both migrations and the K-East seed applied, and the repo secrets `DATABASE_URL` (Session pooler URI; GitHub runners have no IPv6, so the direct `db.<ref>.supabase.co` host won't work from Actions) and `OPENAQ_API_KEY` are set. The 420-day backfill ran on Oct 11, 2026.
   - The scheduled hourly run uses the workflow on `main`. The secret-check fix (`working-directory: .` on the gate step) must be on `main` or every scheduled run fails at its first step.
   - The workflow runs `init-db` before `ingest` and `run`, so new migrations reach Supabase on the next hourly run. Keep every migration safe to re-run, and give every new table `enable row level security`.
2. **Verify live data:** weather and OpenAQ station history are verified (see above). Still to do: watch for OpenAQ's CPCB feed to resume and the run's `data_mode` to turn `live`; if it stays stale, add CPCB's own real-time feed (data.gov.in) as a second source. Then run `dusttrace osm` for real schools and hospitals.
3. **Deploy the console** on Vercel, root `apps/web`, env `DATABASE_URL` and `DUSTTRACE_PASSWORD` (the console returns 503 in production without it). Officers use `/officer` on their phones; outcomes feed the next run's ranking (past violations) and the agent (D8/D9).
4. **Calibrate:** compare plume increments with station deltas downwind of real sites, tune the emission factors, and reach about 80% coverage for the quantile band.
5. **Agent cases (PRD D1–D10):** the inspection case builder ranks sites, checks the sensor, satellite and bus evidence, proposes actions, and needs an officer's sign-off.
6. **Site-manager view:** done: `/plan/[siteId]?t=…` (HMAC link per site, `PLAN_SECRET` in production; the console's site page shows the link). Next 24 h holds, best hours, misting from 90 min before each hold, and "Accept plan" (`plan_acceptances`), which feeds "windows followed" in the Dust Score. Next: send the link on WhatsApp.
7. **Resident QR page:** a public Dust Score for each site, plus a report form.
8. **Round 2 report (Dec 1):** use real metrics from step 2, screenshots from `docs/screens/`, and the plume method above. Keep the "demo" and "simulated pilot" labels honest.

## Decisions worth keeping

- PM10 is the primary metric. Construction dust is coarse, and India's 24 h PM10 standard is 100 µg/m³.
- The Safe-Work thresholds are *modelled increments* at receptors, not ambient totals. That way a site is judged on its own contribution.
- Times are stored in UTC and shown in IST. Night hours (22:00–06:00) are dimmed because dusty work is not allowed then.
- Every number on screen that is synthetic or demo is labelled as such.
- Design: dark graphite with amber as the only accent and Manrope only; never blue. See `docs/design-system.md`.
