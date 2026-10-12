# DustTrace design system

One look across the console, the deck, the video and anything new: a near-black graphite console with white type, where **dust amber is the only accent** and marks dust or the one thing to look at. Reference images were the Financia and Nexora dark dashboards. No blue anywhere.

Tokens live in code at `apps/web/app/globals.css` (`:root`). Keep that file and this page in sync.

## Colour

| Token | Hex | Use |
|---|---|---|
| `--ink-black` | `#0B0B0C` | Page and video background |
| `--panel` | `#141416` | Cards, windows, stat tiles |
| `--sunk` | `#1A1A1D` | Inputs, tracks, code |
| `--line` | `#25252A` | 1 px borders, chart grid |
| `--line-2` | `#34343A` | Stronger borders, hover |
| `--text` | `#F2F2F2` | Headlines, values, cursor |
| `--text-2` | `#A3A3A8` | Body copy, secondary lines |
| `--text-3` | `#6F6F75` | Meta, table headers |
| `--dust` | `#E0A245` | Dust, focus ring, the single accent |
| `--dust-mark` | `#C27F26` | Amber for chart lines, bands, plume fills |
| `--avoid` | `#EB6E5B` | Avoid status, critical readings only |
| `--caution` | `#E0A245` | Caution status (same hue as dust) |
| `--go` | `#6CC59A` | Go status, improvements, our nodes |
| `--info` | `#86BDB9` | Monitoring stations, BEST buses |

Each status has a dark tint (`--avoid-tint #2E1714`, `--caution-tint #2B2216`, `--go-tint #14261C`) for pill and banner fills.

Rules:
- Status colours are reserved. Never reuse red, amber or green for an ordinary data series.
- Observed data is grey (`#8E8E94`); forecasts are amber. A chart has at most one amber series.
- Backgrounds get one effect only: a faint amber radial glow top-right (9% in the app, 22% in video).
- Card fill is a very soft white glass gradient over `--panel` (4% → 1.2%). No coloured gradients.

## Type

Manrope only (`@fontsource/manrope`, weights 300–700). Numbers use tabular figures (`.tab`).

| Role | App | Video (1920×1080) |
|---|---|---|
| Hero number | 42 px Light 300, −3% tracking | 220 px Light 300, −5% |
| Page title (h1) | 30 px SemiBold 600, −2.5% | 88 px SemiBold 600, −3.5% |
| Panel title (h2) | 17 px SemiBold 600 | – |
| Body | 14 px Regular, 1.45 | – |
| Lede | 15 px, `--text-2` | Kicker 28 px Medium, muted |
| Meta / labels | 12.5 px, `--text-3` | Scene chip 24 px SemiBold |
| Caption | – | 34 px Medium on 80% black plate, ≤42 chars × 2 lines |

Writing rules: sentence case everywhere. No all-caps eyebrows, no labels stacked above headings, no single accented word in a headline. Name things the way an officer or contractor would ("Hold dusty work", not "Exceedance event"). Always write `µg/m³`. Synthetic or demo data is always labelled on screen.

## Shape and layout

- Card radius 18 px, inner items 14 px, small 10 px, pills and buttons fully round.
- Active nav item is a white pill with black text.
- App shell: 220 px left rail (logo, nav, team footer), 50 px top bar (ward, issued time, data-mode pill), content padding 22–24 px, 16 px gaps.
- Overview grid: main column + 380 px side column; collapses to one column under 1100 px.
- Stat tiles: big light numeral left, two-line description right.
- Focus: 2 px amber outline, 2 px offset.

## Components (in `apps/web`)

| Component | What it shows |
|---|---|
| `TopBar` | Ward name, forecast issue time (IST), data-mode pill: Live (green), Partly synthetic (amber), Synthetic (dust) |
| `DustMap` | MapLibre, OpenFreeMap dark vector basemap (no key; CARTO now needs one); amber plume polygons, white school and hospital dots with labels, small unlabelled grey `#6F6F75` dots for estimated homes, teal stations, site discs coloured by status with the site letter; Play + hour slider; wind and legend line |
| `ForecastChart` | SVG: amber forecast line, 10–90% band at 14% opacity, grey observed line, white line at the 100 standard, "Now" marker, peak label, hover crosshair and tooltip |
| `WindowStrip` | One cell per hour, Go / Caution / Avoid; night hours (22:00–06:00 IST) at 35% |
| `.item` list | 4 px status bar on the left, bold head, muted reason |
| `.banner` | Amber outline on dust tint, for honesty notices (synthetic data) |
| `.pill` | Status or mode chip; tinted fill + coloured border |
| `.meter` | Priority score as segments, one per component; upwind is the one amber segment, the rest are greys, with a key below |
| `.meter.split` | Data check: where the run's station hours came from. Measured is light grey `#C9C9CE`, filled from CAMS is amber `--dust-mark`, synthetic is dark grey `#4A4A50`; key below with percentages |
| Public site page (`/s/[id]`) | No console rail; one 640 px column, phone first. Big light score numeral, band pill (Good go, Fair caution, Poor avoid), grey part bars, demo banner, 44 px report choices |
| `TrustPill` | Sensor trust score and band: Trusted (go), Check (caution), Untrusted (avoid); "No sensor" plain |

## Charts

- Amber `#C27F26` for the mark, the band is the same amber at 14%.
- Grid lines `#25252A`, axis text 12 px `#8E8E94`; y ticks every 50 (100 when the max exceeds 300).
- Reference lines (standards) are white at 50% with a plain label, never red.
- Label the peak directly on the chart instead of relying on a legend.
- Times are IST. x labels every 6 h; midnight gets the weekday.

## Motion

- One easing curve: `cubic-bezier(0.2, 0.7, 0.2, 1)`.
- Entrances: 400 ms fade with a 24 px rise. Nothing spins, bounces or swipes.
- Motion only for user actions (Play on the map, hover) in the app. No scroll-triggered effects.

## Video spec (pitch film and teaser)

- 1920×1080, 30 fps, H.264. 4K masters possible (all screens captured at 3840×2160).
- Every frame: amber glow top-right, scene chip top-left at (96, 72), product in a floating window (18 px corners, 1 px border, deep shadow, no fake browser bar), one focus point, caption plate 64 px from bottom.
- Focus: spotlight dims the rest to 58% and draws a 2 px amber ring, eased over 300 ms.
- Taps: 30 px white cursor with an amber ripple.
- Numbers count up over 1.2 s; charts draw left to right over 1.5 s; product shots push in 3–5%.
- Transitions: 0.4 s crossfade inside an act, 0.3 s dip to black between acts, hard cut into the end card.
- Audio: voice around −16 LUFS, music 12 dB under.
- Full storyboard: `docs/video/storyboard.md`. Renderer used for the teaser: `docs/video/tools/anim2.py`.

## Slides

The deck (`docs/pitch/deck-source`) uses the same tokens at 1920×1080: Manrope, ink-black background, amber glow, glass cards, amber chart marks. `deck.json` gives the slide order: 16 pitch slides then 7 backups (A1–A7).
