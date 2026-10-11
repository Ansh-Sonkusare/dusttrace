# DustTrace pitch video: storyboard and design scheme

Oct 2, 2026 · @Teak

A 2-minute product film that follows one day in K-East: dust predicted tonight, prevented at dawn, proven by noon. It has 14 scenes and about 250 words of voiceover, and every shot comes from the working prototype.

## Spec

| Item | Choice |
| --- | --- |
| Length | 2:00, 14 scenes |
| Format | MP4, H.264, 1920×1080, 30 fps; a 4K master is possible because every source is captured at 3840×2160 |
| Audience | InnovateX judges, watching once, often without sound |
| Goal | Show the full loop in one story: predict, prevent, prove |
| Voice | One narrator, calm, about 125 words a minute, around 250 words in all |
| Captions | Burned in, every voiceover line, so it works muted |
| Music | Ambient electronic bed, about 90 BPM, royalty-free, ducked under the voice |
| Look | The dark DustTrace console: near-black, white type, dust amber as the only accent |
| Honesty | Prototype screens carry "Demo data", and the impact scene says "simulated pilot" on screen |

## Story

One ward, one day, one case. The viewer follows a single forecast from the officer's screen to the contractor's phone, then sees the air get measured.

| Act | Time | Scenes | What the viewer learns |
| --- | --- | --- | --- |
| 1. The problem | 0:00–0:17 | 01–02 | Mumbai mandated sensors, but a sensor only reports dust after it arrives |
| 2. Meet DustTrace | 0:17–0:44 | 03–05 | It forecasts tomorrow's dust site by site and shows where it will drift |
| 3. Prevent | 0:44–1:23 | 06–09 | Alerts carry fixes, an agent builds the case, an officer approves, the site accepts a plan |
| 4. Trust and reach | 1:23–1:44 | 10–12 | Safe-Work Windows, a public Dust Score, our own nodes and bus sensors, residents' QR reports |
| 5. Prove | 1:44–2:00 | 13–14 | Cases close only on a measured drop; the closing line |

## Storyboard

Each scene shows its designed keyframe. The caption on every frame is the voiceover line, burned in. Timecodes add up to 2:00.

### 01 Cold open, 0:00–0:08

[Keyframe: Scene 01: bar chart of sites, sensors installed, sensors reaching BMC, and sensors switched off]

- **Voiceover:** "Mumbai has about twelve hundred active construction sites, and each must now run a dust sensor."
- **Motion:** Bars grow one after another, 0.12 s apart: about 1,200 sites, 662 sensors installed, about 400 reaching BMC's dashboard (amber, the point), and 117 found switched off.
- **Assets:** keyframes/k01.png

### 02 The gap, 0:08–0:17

[Keyframe: Scene 02: winter PM2.5 in five wards against the standard of 40]

- **Voiceover:** "But a sensor only tells you the air is already bad. By then, the dust has reached the school next door."
- **Motion:** Five ward bars grow, then the standard line at 40 fades in across them, so the gap reads at a glance.
- **Assets:** keyframes/k02.png. Figures come from deck slides 3–4: 45% sensored by October 2025, 117 sensors off in the November drive, and PM2.5 of 70–80 µg/m³ against a standard of 40.

### 03 Meet DustTrace, 0:17–0:24

[Keyframe: Scene 03: logo and Predict, Prevent, Prove]

- **Voiceover:** "DustTrace stops construction dust before it reaches people. Predict, prevent, prove."
- **Motion:** The monitor mockup fades in at 16% behind. The logo ring draws on, and the three words land on the beat, with Prevent turning amber.
- **Assets:** keyframes/k03.png, hero/h1-overview-monitor.png

### 04 The morning briefing, 0:24–0:34

[Keyframe: Scene 04: 48-hour PM10 forecast with the Avoid window and 78% annotation]

- **Voiceover:** "Thursday morning in K-East. The forecast gives a seventy-eight percent chance that PM10 crosses the national standard tomorrow, from seven to eleven."
- **Motion:** The forecast line and its likely range draw left to right over 2.5 s. The Avoid window shades in, then the 78% annotation lands on the Friday 09:00 peak.
- **Assets:** screens-4k/01-overview-0800.png

### 05 Dust weather, 0:34–0:44

[Keyframe: Scene 05: the forecast map with a big hour counter]

- **Voiceover:** "Each plume is a forecast from one construction site, carried by tomorrow's wind over a school and a hospital."
- **Motion:** Thirteen hourly frames crossfade at 0.6 s each, so the plumes grow and drift. The big counter ticks 06:00 to 18:00.
- **Assets:** frames-4k/overview-0600 to overview-1800, cropped to the map panel

### 06 One-tap fix, 0:44–0:52

[Keyframe: Scene 06: the critical alert with the cursor on Turn on mist]

- **Voiceover:** "Every alert carries its fix. Site B is spiking with its mist off. One tap, and it's on."
- **Motion:** The cursor glides to "Turn on mist" and clicks at 4 s with a ripple. The card crossfades to its handled state. The music lifts here as Act 3 starts.
- **Assets:** detail/d04-alert-critical.png, then detail/d05-alert-handled.png

### 07 The agent builds a case, 0:52–1:07

[Keyframe: Scene 07: agent steps and first versus final plan]

- **Voiceover:** "For Site A, our agent opens a case on its own. It checks the site sensor, our school node, a passing BEST bus and satellite images, and ranks the causes. No gate photo by nine, so it adds an inspection."
- **Motion:** The steps reveal top-down, 120 ms each. At 9 s the spotlight moves to "What changed", then the shot pans right across the two plans.
- **Assets:** detail/d06-agent-steps.png, detail/d07-likely-causes.png, detail/d08-actions-first-vs-final.png

### 08 Officer signs off, 1:07–1:13

[Keyframe: Scene 08: cursor on Approve inspection]

- **Voiceover:** "Anything stronger than a reminder needs a ward officer's sign-off."
- **Motion:** A close-up on the final plan. The cursor clicks "Approve inspection" and the card crossfades to Approved, with the toast.
- **Assets:** detail/d19-case-approve-click.png, then screens-4k/07-case-approved.png

### 09 The site's plan, 1:13–1:23

[Keyframe: Scene 09: two site-manager phones]

- **Voiceover:** "The contractor gets a plan the evening before: avoid seven to eleven, dig in the afternoon. One tap to accept."
- **Motion:** The phones rise in at a 3° tilt. On "one tap", the right phone's button is pressed and it switches to Accepted.
- **Assets:** phone/p3-manager-plan.png, phone/p4-manager-accepted.png

### 10 Safe-Work Windows, 1:23–1:31

[Keyframe: Scene 10: window strip, Dust Score 64, mist curtain]

- **Voiceover:** "Every site gets Safe-Work Windows and a public Dust Score that rises when it follows them."
- **Motion:** The slots light up left to right, 60 ms each, then 64 counts up. The mist toggle flips to On.
- **Assets:** detail/d11-safe-work-windows.png, detail/d12-capture-and-clean.png, screens/09-site-A-mist-on.png

### 11 Trust the sensors, 1:31–1:38

[Keyframe: Scene 11: bus readings and sensor trust table]

- **Voiceover:** "Our low-cost nodes and sensors on BEST buses check whether each site's own sensor can be trusted."
- **Motion:** The bus readings wipe on along the route, then the spotlight lands on the flagged Site C row.
- **Assets:** detail/d16-bus-readings.png, detail/d15-sensor-health.png

### 12 Residents report, 1:38–1:44

[Keyframe: Scene 12: resident phone with report sent]

- **Voiceover:** "Residents scan the site's QR code to see its score and report dust."
- **Motion:** The phone slides in showing the score. A tap on "Dust cloud" and "Send report" leads to the sent confirmation.
- **Assets:** phone/p1-resident.png, phone/p2-resident-sent.png

### 13 Prove it, 1:44–1:54

[Keyframe: Scene 13: K-East versus control wards, weekly PM10, and −11%]

- **Voiceover:** "And a case only closes when the air measurably improves. We'll prove it against control wards in a pilot."
- **Motion:** Both lines draw left to right over 1.7 s, and the K-East line splits away from the control wards after "Pilot starts". End labels 148 and 125 appear, then −11% counts up. The words "simulated pilot" stay on screen throughout.
- **Assets:** detail/d17-impact-did-chart.png, screens/16-impact.png

### 14 Close, 1:54–2:00

[Keyframe: Scene 14: the closing line with Team ARA IGNITE]

- **Voiceover:** "Mumbai already paid for the sensors. DustTrace turns them into prevention."
- **Motion:** A hard cut. The first line appears, the amber line follows 0.5 s later, and the frame holds 2 s with the music resolving.
- **Assets:** keyframes/k14.png, credited to Team ARA IGNITE: Ansh, Dhruv, Anuj, Sarang

## Design scheme

The film looks like the product: a near-black console with white type, where amber marks dust and nothing else. Every frame uses the same five ingredients: a faint amber glow top-right, a scene chip top-left, the product in a floating window, one focus point, and a caption plate.

### Colour

| Token | Hex | Use |
| --- | --- | --- |
| Ink black | #0B0B0C | Background of every frame |
| Panel | #141416 | Cards, windows, stat tiles |
| Line | #25252A | 1 px borders |
| Text | #F2F2F2 | Headlines, captions, the cursor |
| Muted | #A3A3A8 | Kickers and secondary lines |
| Dust amber | #E0A245 | Dust, the focus ring, the word "Prevent"; nothing decorative |
| Alert red | #EB6E5B | Critical readings only |
| Clean green | #6CC59A | Improvements, Go windows, our nodes |
| Glow | Amber at 22% opacity | One radial glow, top-right; the only background effect |

No blue anywhere, and no gradients on cards.

### Type

One family, Manrope, in five roles.

| Role | Size and weight | Rule |
| --- | --- | --- |
| Hero number | 220 px, Light 300, tracking −5% | At most one per scene |
| Headline | 88 px, SemiBold 600, tracking −3.5% | Two lines at most |
| Kicker | 28 px, Medium 500, muted | Sentence case, never all caps |
| Caption | 34 px, Medium 500, on an 80% black plate | 42 characters a line, two lines at most |
| Scene chip | 24 px, SemiBold 600, pill with an amber dot | Top-left at 96, 72 px |

### Layout

- Canvas 1920×1080, with 96 px side margins and the caption plate 64 px from the bottom.
- Product windows have 18 px corners, a 1 px border and a deep shadow, with no fake browser bar.
- Phones sit in 54 px bezels with a dynamic-island notch and a status bar reading 08:40.
- Timecode sits top-right in muted 22 px. It's for the edit and gets removed in the final render.

### Motion

- One easing curve for everything: cubic-bezier(0.2, 0.7, 0.2, 1).
- Entrances are a 400 ms fade with a 24 px rise. Nothing spins, bounces or swipes.
- Every product shot has a slow push-in of 3–5% over the scene.
- Focus uses a spotlight: dim the rest to 58% and draw a 2 px amber ring, eased in over 300 ms.
- Taps use a 30 px white cursor with an amber ripple and a soft click sound.
- Numbers count up over 1.2 s, and charts draw left to right over 1.5 s.

### Transitions and audio

- 0.4 s crossfades inside an act, a 0.3 s dip to black between acts, and a hard cut into the end card.
- Voice at about −16 LUFS. Music sits 12 dB under the voice, lifts when Act 3 starts at 0:44 and resolves at 1:54.

## Asset kit

Two zips hold every source the edit needs: dusttrace-video-kit.zip has the 1080p material, and dusttrace-4k-sources.zip has the two 4K folders. All of it was captured from the live prototype on demo data.

| Folder | What's inside | Files | Size |
| --- | --- | --- | --- |
| keyframes/ | The designed frame for each scene below | 14 | 1920×1080 |
| screens/ | Every console view and state, ready to drop in | 19 | 1920×1080 |
| screens-4k/ | The same screens for push-ins without blur | 19 | 3840×2160 |
| frames-4k/ | The overview at each hour from 06:00 to 18:00, for the moving plumes | 13 | 3840×2160 |
| detail/ | Close-ups of single panels: alerts, agent steps, plans, charts | 19 | 2× crops |
| phone/ | Resident and site-manager app states | 5 | 1290×2796 |
| hero/ | Monitor and phone mockups in perspective | 5 | 3840×2160 |

## Before we render

Once these are settled, ask Claude to "make the pitch video from the storyboard". It renders the MP4 from this plan and the kit, with captions, a temporary voice and the music cues.

- [ ] Team name for the end card: done, Team ARA IGNITE (Ansh, Dhruv, Anuj, Sarang), no institution
- [ ] Who narrates: record each scene's line as its own clip on a phone, in a quiet room, named 01.m4a to 14.m4a
- [ ] Any length or format limit in the Techfest brief: not checked yet; this plan assumes 2:00
- [ ] Music track: pick a royalty-free one (for example from the YouTube Audio Library) and note its name for credits
- [ ] Keep the "Demo data" and "simulated pilot" labels on screen (recommended)
