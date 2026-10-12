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
- `backtest.py` (F3 evidence): trains on data before the test window only, then issues one forecast a day with only readings up to that origin visible; scores MAE, exceedance F1 and 10–90% coverage against persistence for 1–24 h and 25–48 h ahead, and replays the worst day. Uses only real station readings when any exist. `python -m dusttrace backtest --days 60` or the "Back-test" workflow; results in `backtests` and on the Forecast page. Caveat stated with the results: weather at the target hour is observed (a perfect weather forecast).
  - **Supabase run, Oct 12 (data_mode live: real CPCB readings and real weather), 11 stations, 58 daily forecasts, Aug 8 – Oct 7, 2026:** MAE 8.9 vs 12.4 µg/m³ for persistence at 1–24 h and 9.3 vs 13.5 at 25–48 h; exceedance F1 0.59 vs 0.17 (persistence 0.0 at 25–48 h); 91–93% inside the 10–90% band; the worst day (Oct 2, ward mean 104) was flagged 42 h ahead at p = 0.64 (forecast mean 101). Exceedances were rare in the monsoon (3.4% of hours), so rerun in winter.
- `discover.py` (F2): Sentinel-2 L2A change from the public COGs (Element84 Earth Search, no key). The clearest dry-season scene this year against the same months a year earlier; BSI up and NDVI down outside clouds (SCL) give patches ≥ 2,500 m². Matches within 300 m of a site confirm it is active and become the agent's "satellite change" signal (with D6 that registers an unsensored site); unmatched ones are listed on `/inspect` as unverified. `python -m dusttrace discover`, monthly workflow `discover.yml`. Jan 2025 vs Feb 2026 gave 72 candidates; precision/recall against the demo positions means nothing until real sites are hand-labelled.
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
- **CAMS fill (issue #28):** every ingest stores Copernicus CAMS PM (Open-Meteo Air Quality API, no key) at each real station for the last 70 days plus 3 days ahead in `cams_hourly`, never in `readings`. When a real station is stale (but silent for under 30 days), `pipeline.fill_from_cams` fits a per-station linear correction on its last 60 days of overlap and fills the hours since its last reading, flagged `filled`. The model trains on measured hours only. `data_mode` is `filled` (pill "Real stations, recent hours model-filled").
  - Live on Supabase (run 8, Oct 12 04:00 UTC): all 11 real CPCB stations filled for the 119 h since Oct 7 13:00 UTC; per-station corrections and their fit error are in `runs.metrics.filled`.
  - Verified by `dusttrace replay-outage` on real Sep–Oct 2026 data (29 forecasts, 8 stations, last 96 h hidden): MAE 14.0/15.0 µg/m³ (1–24 h / 25–48 h) with the fill vs 10.1/11.6 with the real data, 13.8/14.2 for corrected CAMS alone and 17.1/17.9 for the last value carried forward. The fill caught none of the rare hours above 100 (F1 0), so treat spike calls during an outage with care.
- **Freshness rule (`pipeline.anchor`, `FRESH_HOURS = 6`):** real stations anchor the forecast only while their newest reading is under 6 h old. Otherwise the seed stations' synthetic readings anchor it, so a stalled feed can't push the 48 h forecast into the past, and the run is `mixed`. The switch to real stations is automatic once OpenAQ catches up.
- The hourly job loads 3 days. After an outage longer than that, run the workflow by hand with more `days` to fill the gap.
- **Overpass works through a mirror** (overpass-api.de resets connections; `sources/overpass.py` falls back to kumi.systems and mail.ru). The bbox plus about 1 km gives about 230 schools and hospitals. Clinics, dental, diagnostic centres and unnamed "hospitals" are dropped, since OSM in Mumbai tags many of them `amenity=hospital`. A weekly workflow (`receptors.yml`) refreshes them.

- **Real construction sites (issue #30):** `dusttrace osm-sites` (weekly, in `receptors.yml`) adds sites mapped in OSM inside the ward (`landuse=construction`, `building=construction`; 1,000–300,000 m²) with `source='osm'`, `demo=false`, `sensor_status='not_connected'`. When every Overpass mirror is down (all three failed on Oct 12, from Actions too), or a mirror answers with no sites (mail.ru did, for a ward with ~22), and likewise for schools and hospitals (ohsome gives 228 against Overpass's 232 under the same rules), the pull falls back to the ohsome API snapshot (`sources/ohsome.py`, same ids); on Oct 12 it returned 22 real sites in K-East, which got 48 h windows and four D3 receptor alerts in a local real-data run. Officers can also confirm a Sentinel-2 candidate on Inspect today, which adds it as `sat-<id>` (`source='satellite'`). A site whose monitor feed isn't connected is *unknown*, not *unmonitored*: no D6, no "no monitor" points in the ranking, and its Dust Score counts the trust share as half. `DUSTTRACE_DEMO_SITES=0` drops the demo sites A–F (and their simulated sensors) from runs.

- **Real housing (issue #31):** `dusttrace osm-housing` (weekly) spreads K/E's Census 2011 population (823,885; census wards 1249, 1255 and 1256, Primary Census Abstract via data.opencity.in) over the residential land mapped in OSM, cell by cell: the ohsome API returns `landuse=residential` area clipped to each ~250 m cell of the ward box plus 1 km. On Oct 12: 8.6 km² of homes in the ward (about 95,800 people per km² of homes), 622 cells with at least 3,000 m², 812,750 people in the ward's cells vs the census 823,885 (cells under 3,000 m² are dropped). Each cell is a `housing` receptor named "Homes for about N people (estimated)" and replaces the demo housing points. Caveats: the ward box is not the ward boundary, unmapped informal settlements get no one, and 2011 understates today. A run with 22 real sites and 855 receptors takes about 95 s.
- Real sites go by their name in the console and alerts; only the demo sites A–F show their one-letter code (on the map too).
- **Cause from PM10/PM2.5 and the F10 playbook (issue #34):** each run computes, per real station, the signature of its last 6 measured hours against its own 30-day medians (`signature.py`): a spike (PM10 ≥ 1.5× median) where PM2.5/PM10 drops below 0.8× its median is coarse (working hours: digging or demolition; 22:00–06:00 IST: truck track-out), above 1.2× is fine (combustion). Filled CAMS hours never count. Each site takes the nearest signature within 4 km; it reweights the agent's cause hypotheses but is never counted as a D1 signal, since a station is shared by many sites. Playbook actions (all to the site): ORDER_WHEEL_WASH when track-out is the top cause, ORDER_COVER_DEBRIS (2 h deadline) when uncovered debris is, PRE_WET_SITE on coarse working-hour dust and on dry, windy days ahead (working hours with wind ≥ 5 m/s and no rain in the past 24 h; about 10% of real hours, mostly July). D10 still drops them for a non-construction source.
  - On real CPCB data: of 6,801 spike hours, 34% coarse (peaking 21:00–01:00 IST), 22% fine, 45% mixed. Replaying the signature every 6 h through Sep–Oct 7 gave 32 coarse, 72 fine and 60 mixed station-checks out of 687. Pairs with PM2.5/PM10 under 0.05 or over 1 are broken channels and ignored (seen on Sep 1). While the CPCB feed is down, no signature is computed.
- **Verify step (issue #33):** each run checks every dust-cutting action (mist, pre-wet, pause, cover, wheel wash, Safe-Work Windows) whose 6 h window has passed: PM10 at the nearest real station within 4 km that sat downwind of the site, against the same IST hours on up to 21 earlier days with wind from the same 45° sector (`effect.py`). At least 10% lower closes the case ("Verified: …"); otherwise it stays open. No readings in the window, or fewer than 3 comparable days, is "insufficient", never assumed. Results land in `verifications` and on the Cases page ("Did the fixes work?"), with the average change per action. While the CPCB feed is down, every check is insufficient.
- **CAMS as a forecast feature (issue #32):** `backtest --compare-cams` (Back-test workflow, kind `cams`) runs the same window with and without CAMS PM10 at the target hour and its 24 h mean. First real run (Sep 7–Oct 7, 11 stations, 29 forecasts, only Aug–Sep CAMS in training): MAE 10.16 → 10.49 (1–24 h) and 10.77 → 11.18 (25–48 h), F1 0.559 → 0.596 and 0.615 → 0.589. Net slightly worse, so production stays without it.
- New migrations reach Supabase on push to main (`migrate.yml`), so a deploy that reads a new table doesn't 500 while waiting for the hourly job (it did once, for `api_requests`).
- **Weekly ward report and public API (issue #37):** the console's Weekly report page (`/report`, prints to PDF) covers the last 7 days: day-ahead spike calls (the forecast issued 12 h or more before each hour, P ≥ 0.6) against the ward mean of measured station hours, case actions by rule, inspection outcomes, fix checks and Dust Scores, each with its source. The public read-only API needs no password: `/api/public/v1/forecast`, `/api/public/v1/windows` and `/api/public/v1/dust-scores`. Their shapes are explicit (no receptor names, people counts, notes or reports), responses are cached at the edge for 5 minutes, and each address gets 120 requests an hour (salted hash in `api_requests`, pruned daily). On the real-data copy the first report shows Wed 7 Oct as a missed spike: measured above 100, not forecast.
- **Data check (issue #29):** the hourly job ends with `dusttrace verify`, which stores a `data_checks` row for the latest run: each real station's newest PM10 reading (fresh / stale / silent), the share of the last week's station hours that were measured vs CAMS-filled vs synthetic (`runs.metrics.inputs`), the CAMS fill's error on each station's last 30 real days (correction fitted only on earlier days), and the state of weather, receptors, sites and Sentinel-2. The console's **Data check** page shows it; the overview banner links there.
  - First check on the real data (local copy, Oct 12): 31% of the last week measured, 69% filled; hold-out fill error median 20 µg/m³ across 8 stations, and the fill reads low at every station (bias −0.7 to −17.6), likely because PM10 is rising out of the monsoon and the correction is fitted on wetter weeks. Tested on 56 rolling 96 h fills across the last month: fitting on 7/14/21/30/60 days gives MAE 25.0/19.5/20.1/20.5/20.7 and bias +0.6/−8.5/−8.4/−8.2/−10.5, so a shorter window doesn't fix it; the fill keeps 60 days. A weather term in the correction, or CAMS as a forecast feature, is the next thing to try (issue #32).

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
   - The workflow runs `init-db` and `seed` (both safe to re-run) before `ingest` and `run`, so new migrations and seed entries reach Supabase on the next hourly run. GitHub's schedule is best-effort and skipped several hours on Oct 12; run the workflow by hand when the console looks stale. Keep every migration safe to re-run, and give every new table `enable row level security`.
2. **Verify live data:** weather and OpenAQ station history are verified (see above). Still to do: watch for OpenAQ's CPCB feed to resume and the run's `data_mode` to turn `live`; if it stays stale, add CPCB's own real-time feed (data.gov.in) as a second source. Then run `dusttrace osm` for real schools and hospitals.
3. **Console deployed (Oct 12, 2026):** https://dusttrace-mumbai.vercel.app (Vercel project `dusttrace` on Ansh's account, linked to this repo; every push to `main` deploys to production, PR branches get previews).
   - Root `apps/web`, Next.js, functions in `bom1` (Mumbai, next to Supabase). Vercel's own deployment protection is off so residents can open `/s/…`; the console is behind `DUSTTRACE_PASSWORD`.
   - Env (production and preview): `DATABASE_URL` (Supabase **transaction** pooler, port 6543, for serverless), `DUSTTRACE_PASSWORD`, `PLAN_SECRET`, `REPORT_SALT`, `PUBLIC_BASE_URL=https://dusttrace-mumbai.vercel.app`, `DUSTTRACE_WARD=K-East`. Values live only in Vercel; change them there (and redeploy) to rotate.
   - Officers use `/officer` on their phones; outcomes feed the next run's ranking (past violations) and the agent (D8/D9).
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
