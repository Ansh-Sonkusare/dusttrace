# DustTrace Node

A low-cost PM monitor for the roof or gate of a school, hospital or housing society (PRD F9). It sends PM2.5 and PM10 every minute to `POST /api/node`. The readings land in `node_readings`, corrected for humidity on the server.

## Parts

- ESP32 dev board
- Plantower PMS5003 (PM sensor)
- Sensirion SHT31 (humidity and temperature, needed for the correction)
- A 5 V supply from the host building, which also provides the Wi-Fi

Wiring and the firmware are in [`dusttrace-node.ino`](dusttrace-node.ino), written for Arduino-ESP32 core 3.x. It has not been compiled in CI.

## Provision a node

Each node has its own key. The server stores only its SHA-256.

```bash
cd services/engine
python -m dusttrace --ward K-East node-add --id node-marol-school --name "Marol school roof" \
  --host-kind school --lat 19.1172 --lon 72.8790 [--receptor <receptor id of the school>]
```

The command prints the key once. Paste it into `NODE_KEY` in the sketch. Running `node-add` again for the same id rotates the key, and the old key stops working.

A node at a construction site's gate takes `--host-kind site_gate --site <site id>`. Its readings are the evidence that a site ignored a Safe-Work Window (D8): an Avoid hour of a plan the manager accepted, in which the gate node read PM10 above twice the ambient. Without a gate node, no window is ever counted as ignored.

## API

`POST /api/node`, header `Authorization: Bearer <key>`, JSON body:

```json
{"node_id": "node-marol-school",
 "readings": [{"ts": "2026-11-22T09:58:00Z", "pm25": 40, "pm10": 80, "rh": 60, "temp": 29}]}
```

- 1 to 60 readings per post, so a node can send an hour it buffered while offline.
- `pm25` and `pm10` are required, in µg/m³, from 0 to 2,000, with PM2.5 not above PM10. `rh` (0–100) and `temp` (−10 to 60 °C) are optional.
- `ts` is optional, ISO 8601, within the last 48 hours. Without it the server's clock is used. It is stored to the minute.
- The answer is `{"accepted": n, "duplicate": m}`. A minute already stored is ignored, so re-sending a batch is safe. Errors: 400 for a bad body, 401 for an unknown node or a wrong key.

[`simulate_node.py`](simulate_node.py) sends the same payload from a laptop to check a deployment.

## What the numbers mean

- **Humidity.** An optical sensor counts water-swollen particles as dust. The server divides by the growth factor C = 1 + (κ/1.65)·a_w/(1 − a_w), with a_w = RH/100, 1.65 the particle-to-water density ratio and κ = 0.3 (Crilley et al. 2018, Atmos. Meas. Tech. 11:709, Eq. 5; 0.3 is the paper's value for a site with no co-located reference). The paper fits only below 95% RH, where the humidity sensor's own error stays small, so above that the corrected value is left empty and the raw value kept. Fitting κ per node against the nearest CPCB station would tighten it.
- **PM10 is the weak spot.** The PMS5003 estimates PM10 from particles it sizes mostly below 2.5 µm, so it under-reads coarse construction dust. Treat a node's PM10 as a relative signal for its own spot, not a regulatory number. Calibrate each node against the nearest CPCB station before comparing absolute values.
