# Smart Wastebin System

> An IoT edge-computing pipeline that monitors bin occupancy via a PIR motion sensor,
> publishes structured events over MQTT, stores them in SQLite, classifies usage intensity
> with rule-based and ML virtual sensors, exposes a REST API with Swagger UI and AsyncApi,
>  utilizes Node-RED for low code integration
> as well as Cloudflare Tunnel for easy acess and surfaces
> all entities in Home Assistant — all in a single `docker compose up --build`.

**Team 08** · Advanced Programming Techniques ECE Upatras · 2026

---

## Table of Contents

1. [Architecture overview](#1-architecture-overview)
2. [Hardware & wiring](#2-hardware--wiring)
3. [Prerequisites](#3-prerequisites)
4. [Quick start](#4-quick-start)
5. [Directory structure](#5-directory-structure)
6. [Services reference](#6-services-reference)
7. [MQTT topic structure](#7-mqtt-topic-structure)
8. [REST API endpoints](#8-rest-api-endpoints)
9. [SQLite database](#9-sqlite-database)
10. [Node-RED flows](#10-node-red-flows)
11. [Virtual sensors](#11-virtual-sensors)
12. [Home Assistant integration](#12-home-assistant-integration)
13. [Training data upload & retraining](#13-training-data-upload--retraining)
14. [Cloudflare tunnel (remote access)](#14-cloudflare-tunnel-remote-access)
15. [Configuration reference](#15-configuration-reference)
16. [Extending the system](#16-extending-the-system)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Architecture Overview

```
HC-SR501 PIR sensor
       │ GPIO BCM-17
       ▼
  producer.py ──────────────────► Mosquitto MQTT :1883
       │                                │
  sensor_state.json                     ├──► consumer.py ──► motion_events.jsonl
  (persisted fill level)                │
                                        ├──► virtual_sensor_rules.py  (CEP deque)
                                        │
                                        ├──► virtual_sensor_ml.py     (Random Forest)
                                        │
                                        ├──► Node-RED :1880
                                        │         ├── alert flows
                                        │         └── SQLite writer ──► smartbin.db
                                        │
                                        └──► api.py :5000 (Swagger UI)
                                                   ├── /bins/{id}/events
                                                   ├── /bins/{id}/peak-hour
                                                   ├── /bins/{id}/hourly-activity
                                                   └── /mqtt/...
                                                         │
                                               Home Assistant :8123
                                                         │
                                               Cloudflare Tunnel
                                               ha / api / upload / asyncapi
                                               .yourdomain.com
```

---

## 2. Hardware & Wiring

### Components

| Component | Quantity | Notes |
|---|---|---|
| Raspberry Pi 4 (or 3B+) | 1 | Any model with 40-pin GPIO header |
| HC-SR501 PIR Motion Sensor | 1 | 3–20 V supply, 3.3 V output — Pi-compatible |
| Female-to-female jumper wires | 3 | |
| Waste bin (~18 cm height) | 1 | Sensor mounts at the back of the bin's body |

### GPIO Wiring

```
HC-SR501 Pin          Raspberry Pi Pin (BCM)    Raspberry Pi Header Pin
─────────────────────────────────────────────────────────────────────────
VCC  (power)    ──►   5 V                        Pin 2
GND  (ground)   ──►   GND                        Pin 6
OUT  (signal)   ──►   GPIO 17 (BCM)              Pin 11
```

#### Raspberry Pi GPIO header reference (relevant pins)

```
         3.3V  [1]  [2]  5V       ← use pin 2 for HC-SR501 VCC
          SDA  [3]  [4]  5V
          SCL  [5]  [6]  GND      ← use pin 6 for HC-SR501 GND
     GPIO  4   [7]  [8]  TX
          GND  [9] [10]  RX
★   GPIO 17  [11] [12]  GPIO 18  ← use pin 11 for HC-SR501 OUT
    GPIO 27  [13] [14]  GND
    ...
```


### Physical mounting (cross-section view)

```
        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ← bin lid
        ┌──────────────────┐
        │   HC-SR501 dome  │  ← mounted on the back
        └────────┬─────────┘
                 
        
        │                    │
        │       BIN          │  
        │    interior        │
        │                    │
        └────────────────────┘
```

---

## 3. Prerequisites

### On the Raspberry Pi

| Requirement | Version | Check |
|---|---|---|
| OS | Raspberry Pi OS Lite (Bookworm 64-bit) | `uname -a` |
| Docker Engine | ≥ 24 | `docker --version` |
| Docker Compose plugin | ≥ 2.20 | `docker compose version` |
| Git | any | `git --version` |
| Node.js (for AsyncAPI CLI, optional) | ≥ 18 | `node --version` |

#### Install Docker on Raspberry Pi (if not installed)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

### For remote access (optional)

- A Cloudflare account (free)
- A domain registered on or transferred to Cloudflare (~$10/year)
- `cloudflared` CLI installed (see [Section 14](#14-cloudflare-tunnel-remote-access))

---

## 4. Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/manos-max/Smart-Waste-Bin.git
cd smartbin

# 2. (Raspberry Pi only) Ensure GPIO device exists
ls /dev/gpiochip0

# 3. Generate AsyncAPI static docs (optional, requires Node.js)
npm install -g @asyncapi/cli
asyncapi generate fromTemplate asyncapi.yml @asyncapi/html-template \
  --output asyncapi-docs

# 4. Start everything
docker compose up --build

# Services come up at:
#   Swagger UI          →  http://localhost:5000
#   Upload & charts     →  http://localhost:5001
#   AsyncAPI docs       →  http://localhost:5002
#   Node-RED editor     →  http://localhost:1880
#   MQTT broker         →  localhost:1883
```


---

## 5. Directory Structure

```
smartbin/
├── README.md
├── requirements.txt
├── asyncapi.yml                  ← AsyncAPI 3.0 MQTT interface spec
├── Dockerfile
├── docker-compose.yml
├── mosquitto.conf
├── train_model.py                ← train/retrain ML model (run at build time)
├── virtual_sensor_ml.py
├── virtual_sensor_rules.py
│
├── src/                          ← Python application code
│   ├── api.py                    ← Flask-RESTx REST API
│   ├── consumer.py               ← MQTT subscriber + JSONL writer
│   ├── producer.py               ← GPIO reader + MQTT publisher
│   ├── upload.py                 ← CSV upload + seaborn visualisation
│   ├── serve_yaml.py             ← AsyncAPI YAML static server
│   └── pirlib/
│       ├── __init__.py
│       ├── interpreter.py        ← debounce + cooldown logic
│       └── sampler.py            ← lgpio GPIO abstraction
│
├── models/                       ← JSON-LD semantic model files
│   ├── context.jsonld
│   ├── wastebin.jsonld
│   ├── sensor.jsonld
│   └── environment.jsonld
│
├── models_v_s/                   ← trained ML artefacts (generated at build)
│   └── busy_predictor.joblib
│
├── node-red/                     ← Node-RED configuration (version-controlled)
│   ├── flows.json                ← ALL flows — import/export via UI or CLI
│   └── settings.js               ← Node-RED settings (port, logging, etc.)
│
├── db/
│   └── schema.sql                ← SQLite schema — run once on first boot
│
├── docs/
│   └── Ontology                  ← ontology documentation
│
├── asyncapi-docs/                ← generated static HTML (gitignored)
│
└── data/                         ← runtime data (gitignored)
    ├── motion_events.jsonl
    ├── emptied_records.jsonl
    ├── sensor_state.json
    ├── smartbin.db
    └── uploads/
```

### `.gitignore` essentials

```gitignore
# Runtime data — never commit
data/
asyncapi-docs/

# Cloudflare credentials — never commit
.cloudflared/*.json
.cloudflared/config.yml

# Python
__pycache__/
*.pyc
.venv/

# Secrets
.env
*.secret
```

---

## 6. Services Reference

| Service | Image | Port | Command | Key volumes |
|---|---|---|---|---|
| `mosquitto` | `eclipse-mosquitto:2` | 1883 | — | `./mosquitto.conf` |
| `producer` | project build | — | `python producer.py --verbose --host mosquitto` | `./data` |
| `consumer` | project build | — | `python consumer.py --host mosquitto --topic ... --out ...` | `./data` |
| `api` | project build | **5000** | `python api.py` | `./data` |
| `upload` | project build | **5001** | `python upload.py` | `./data`, `./models_v_s` |
| `asyncapi-docs` | project build | **5002** | `python serve_yaml.py` | `./asyncapi.yml` |
| `virtual_sensor_rules` | project build | — | `python virtual_sensor_rules.py --broker mosquitto` | — |
| `virtual_sensor_ml` | project build | — | `python virtual_sensor_ml.py --broker mosquitto` | `./models_v_s` |
| `node-red` | `nodered/node-red:latest` | **1880** | — | `./node-red:/data` |

### Useful docker compose commands

```bash
# Start all services in background
docker compose up -d

# Follow logs for a single service
docker compose logs -f api

# Restart one service (e.g. after model retrain)
docker compose restart virtual_sensor_ml

# Stop everything and remove containers (data volumes preserved)
docker compose down

# Full reset including named volumes
docker compose down -v
```

---

## 7. MQTT Topic Structure

All topics follow the pattern `smartbin/{bin_id}/{sensor_id}/...`
allowing multi-bin deployment by changing `bin_id` (default: `bin-01`).

| Topic | Publisher | Payload | Retained | QoS |
|---|---|---|---|---|
| `smartbin/bin-01/pir-01/events` | producer | Full JSON-LD Observation | No | 1 |
| `smartbin/bin-01/pir-01/motion` | producer | `detected` \| `clear` | No | 1 |
| `smartbin/bin-01/fill-level/state` | producer | `0`–`100` (string) | No | 1 |
| `smartbin/bin-01/pir-01/events/status` | producer | `online` \| `offline` (LWT) | Yes | 1 |
| `smartbin/bin-01/command` | api | `{action, emptied_at, emptied_by}` | No | 1 |
| `smartbin/bin-01/status` | api | `{state, emptied_at}` | Yes | 1 |
| `smartbin/bin-01/usage` | virtual_sensor_rules / node-red | `{usage_level, event_count, window_minutes}` | Yes | 1 |
| `smartbin/bin-01/prediction` | virtual_sensor_ml | `{prediction, confidence, predicted_hour}` | Yes | 1 |
| `smartbin/bin-01/alert` | node-red | `{type, fill_level, timestamp}` | Yes | 1 |
| `homeassistant/binary_sensor/bin-01_pir-01/config` | producer | HA Discovery JSON | Yes | 1 |
| `homeassistant/sensor/bin-01_fill/config` | producer | HA Discovery JSON | Yes | 1 |
| `homeassistant/sensor/bin-01_usage_level/config` | virtual_sensor_rules | HA Discovery JSON | Yes | 1 |
| `homeassistant/sensor/bin-01_motion_count/config` | virtual_sensor_rules | HA Discovery JSON | Yes | 1 |

### Test with mosquitto CLI

```bash
# Subscribe to all smartbin topics
docker exec -it smartbin-mosquitto-1 \
  mosquitto_sub -v -t 'smartbin/#'

# Inject a synthetic motion event (for testing without Pi)
curl -X POST http://localhost:5000/mqtt/publish \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "smartbin/bin-01/pir-01/events",
    "payload": "{\"motion_state\":\"detected\",\"fill_level\":42,\"item_count\":21,\"seq\":1,\"event_time\":\"2026-01-01T12:00:00Z\",\"device_id\":\"urn:dev:team08:pir-01\",\"@type\":\"sosa:Observation\"}",
    "qos": 1
  }'
```

---

## 8. REST API Endpoints

Base URL: `http://localhost:5000` · Swagger UI: `http://localhost:5000/`

### `/bins` namespace

| Method | Path | Description |
|---|---|---|
| GET | `/bins/` | List all registered bins |
| GET | `/bins/{bin_id}` | Bin detail (name, location, status) |
| GET | `/bins/{bin_id}/events?limit=50` | Recent motion events (SQLite + JSONL fallback) |
| POST | `/bins/{bin_id}/empty` | Mark bin emptied — publishes MQTT command |
| GET | `/bins/{bin_id}/emptied-history?limit=20` | History of emptying events |
| GET | `/bins/{bin_id}/peak-hour` | Hour of day with highest event count (today) |
| GET | `/bins/{bin_id}/hourly-activity` | Event count per hour for today (hours with activity only) |

#### Example — peak-hour response

```json
{
  "bin_id": "bin-01",
  "date": "2026-01-15",
  "peak_hour": 12,
  "peak_hour_label": "12:00–13:00",
  "event_count": 23
}
```

#### Example — hourly-activity response

```json
{
  "bin_id": "bin-01",
  "date": "2026-01-15",
  "intervals": [
    {"hour": 8,  "hour_label": "08:00–09:00", "event_count": 7},
    {"hour": 12, "hour_label": "12:00–13:00", "event_count": 23},
    {"hour": 15, "hour_label": "15:00–16:00", "event_count": 11}
  ]
}
```

### `/sensors` namespace

| Method | Path | Description |
|---|---|---|
| GET | `/sensors/` | List all registered sensors |
| GET | `/sensors/{sensor_id}` | Sensor detail (model, pin, mounted_on) |
| GET | `/sensors/{sensor_id}/events?limit=50` | Events filtered by sensor URI (SQLite) |

### `/mqtt` namespace

| Method | Path | Description |
|---|---|---|
| POST | `/mqtt/publish` | Publish arbitrary message to any topic |
| GET | `/mqtt/topics` | All topics seen since API start (last message each) |
| GET | `/mqtt/topics/{topic}` | Last message on a specific topic |

---

## 9. SQLite Database

### Schema

```sql
-- db/schema.sql  (applied automatically on first run via api.py)

CREATE TABLE IF NOT EXISTS events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bin_id              TEXT    NOT NULL,
    sensor_id           TEXT    NOT NULL,
    event_time          TEXT    NOT NULL,
    ingest_time         TEXT,
    motion_state        TEXT,
    fill_level          INTEGER,
    item_count          INTEGER,
    seq                 INTEGER,
    run_id              TEXT,
    pipeline_latency_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_events_bin_time
    ON events (bin_id, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_events_sensor
    ON events (sensor_id, event_time DESC);

CREATE TABLE IF NOT EXISTS emptied_records (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bin_id     TEXT NOT NULL,
    emptied_at TEXT NOT NULL,
    emptied_by TEXT
);
```

### Direct access

```bash
# Open SQLite shell inside the running api container
docker exec -it smartbin-api-1 sqlite3 /app/data/smartbin.db

# Useful queries
.tables
SELECT COUNT(*) FROM events;
SELECT bin_id, COUNT(*) as n FROM events GROUP BY bin_id;
SELECT * FROM events ORDER BY event_time DESC LIMIT 5;

# Peak hour today
SELECT strftime('%H', event_time) as hour, COUNT(*) as cnt
FROM events
WHERE bin_id = 'bin-01'
  AND DATE(event_time) = DATE('now')
GROUP BY hour
ORDER BY cnt DESC
LIMIT 1;
```

### Backup

```bash
# Copy the database file out of the container volume
docker cp smartbin-api-1:/app/data/smartbin.db ./backup_$(date +%Y%m%d).db
```

---

## 10. Node-RED Flows

Node-RED runs at `http://localhost:1880`.
All flows are version-controlled in `node-red/flows.json` and mounted into the container.

### Importing flows (first run)

Flows are loaded automatically from the mounted volume.
If you need to re-import manually:

1. Open `http://localhost:1880`
2. Hamburger menu → **Import** → **Clipboard**
3. Paste the contents of `node-red/flows.json`
4. Click **Import** → **Deploy**

### Exporting flows after editing

After making changes in the Node-RED UI:

1. Hamburger menu → **Export** → **All flows** → **JSON**
2. Copy and overwrite `node-red/flows.json` in the repository
3. Commit: `git add node-red/flows.json && git commit -m "update node-red flows"`

### What the flows do

| Flow | Subscribes to | Logic | Publishes to |
|---|---|---|---|
| **Event filter + count** | `smartbin/+/+/events` | Parses payload, keeps `detected`, counts in rolling 10-min window | `smartbin/{bin_id}/usage` |
| **Level classification** | (internal, from above) | switch node: idle/low/medium/high | `smartbin/{bin_id}/usage` |
| **Fill level alert** | `smartbin/+/fill-level/state` | switch: value ≥ 80 | `smartbin/{bin_id}/alert` |
| **SQLite writer** | `smartbin/+/+/events` | Builds INSERT, writes row | `smartbin.db` via sqlite node |

### Installing missing Node-RED nodes

If the `node-red-node-sqlite` package is missing after a fresh pull:

```bash
docker exec -it smartbin-node-red-1 \
  npm install --prefix /usr/src/node-red node-red-node-sqlite
docker compose restart node-red
```

This is handled automatically if you add it to the `node-red/settings.js` packages list (see below).

### `node-red/settings.js` — key settings

```js
module.exports = {
    uiPort: 1880,
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,
    debugMaxLength: 1000,
    // Packages to install on startup
    editorTheme: {
        projects: { enabled: false }
    }
}
```

---

## 11. Virtual Sensors

### Rule-based (`virtual_sensor_rules.py`)

Subscribes to `smartbin/bin-01/pir-01/events`, maintains a `collections.deque` as a
10-minute rolling window. Evaluates every 30 seconds.

| Level | Condition |
|---|---|
| idle | count == 0 |
| low | 1 ≤ count ≤ 3 |
| medium | 4 ≤ count ≤ 10 |
| high | count > 10 |

Publishes to `smartbin/bin-01/usage` (retained, QoS 1).

### ML-based (`virtual_sensor_ml.py`)

Loads `models_v_s/busy_predictor.joblib` at startup.
Every 60 seconds, predicts whether the **next hour** will be `busy` or `quiet`.

Features: `hour`, `day_of_week`, `is_weekend`.
Model: `RandomForestClassifier` (50 estimators), trained at Docker build time.
Accuracy: 94% on held-out test set (see classification report in README).

Publishes to `smartbin/bin-01/prediction` (retained, QoS 1).

### Retraining with real data

```bash
# Option A: via upload UI at http://localhost:5001
# Upload a CSV with columns: day_of_week,hour,is_weekend,event_count,label
# Click "Retrain model with latest file"

# Option B: CLI inside the container
docker exec -it smartbin-virtual_sensor_ml-1 python train_model.py

# Option C: from a CSV you collected
docker cp my_real_data.csv smartbin-api-1:/app/data/uploads/
docker exec -it smartbin-api-1 python -c "
import pandas as pd, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
df = pd.read_csv('/app/data/uploads/my_real_data.csv')
X = df[['day_of_week','hour','is_weekend']]; y = df['label']
clf = RandomForestClassifier(n_estimators=50, random_state=42)
clf.fit(*train_test_split(X, y, test_size=.2, random_state=42)[:2])
joblib.dump(clf, '/app/models_v_s/busy_predictor.joblib')
print('Done')
"
docker compose restart virtual_sensor_ml
```

---

## 12. Home Assistant Integration

### Prerequisites

- Home Assistant instance (on the same network or accessible via Cloudflare)
- MQTT Integration installed in HA and pointed at `<Pi IP>:1883`

### Setup

1. In Home Assistant: **Settings → Devices & Services → Add Integration → MQTT**
2. Broker: `<Raspberry Pi IP address>` · Port: `1883`
3. All four sensor entities appear automatically via MQTT Discovery within 30 seconds of starting the system.

### Auto-discovered entities

| Entity | Type | State topic |
|---|---|---|
| `binary_sensor.waste_bin_bin01_motion` | Binary sensor | `smartbin/bin-01/pir-01/motion` |
| `sensor.waste_bin_bin01_fill_level` | Sensor (%) | `smartbin/bin-01/fill-level/state` |
| `sensor.waste_bin_bin01_usage_level` | Sensor | `smartbin/bin-01/usage` (JSON template) |
| `sensor.waste_bin_bin01_motion_count` | Sensor (events) | `smartbin/bin-01/usage` (JSON template) |
| `sensor.waste_bin_bin01_prediction` | Sensor | `smartbin/bin-01/prediction` |
| `binary_sensor.waste_bin_bin01_alert` | Binary sensor | `smartbin/bin-01/alert` |

### Suggested automation — empty bin alert

```yaml
# In Home Assistant configuration.yaml or via UI Automation editor
alias: Notify when bin is nearly full
trigger:
  - platform: numeric_state
    entity_id: sensor.waste_bin_bin01_fill_level
    above: 80
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "Bin bin-01 is {{ states('sensor.waste_bin_bin01_fill_level') }}% full."
```

---

## 13. Training Data Upload & Retraining

Upload service runs at `http://localhost:5001`.

### CSV format

```csv
day_of_week,hour,is_weekend,event_count,label
0,8,0,14,busy
0,9,0,22,busy
0,22,0,1,quiet
5,12,1,3,quiet
```

| Column | Type | Values |
|---|---|---|
| `day_of_week` | int | 0 (Mon) – 6 (Sun) |
| `hour` | int | 0–23 |
| `is_weekend` | int | 0 or 1 |
| `event_count` | int | ≥ 0 |
| `label` | string | `busy` or `quiet` |

### What the upload page shows

After uploading, five Seaborn charts are rendered inline:

- **Class balance** — bar chart of busy vs quiet rows
- **Event count distribution** — KDE density curves per class with threshold line
- **Mean events by hour** — weekday vs weekend line chart
- **Activity heatmap** — day-of-week × hour heat map (YlOrRd palette)
- **Labels by day** — stacked bar chart per weekday

---

## 14. Cloudflare Tunnel (Remote Access)

Exposes four services publicly via HTTPS with no open router ports.

### Step 1 — Buy domain

Cloudflare Dashboard → Domain Registration → Register Domains → choose `yourdomain.com`

### Step 2 — Install cloudflared on Pi

```bash
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflare-workers-proxy focal main" \
  | sudo tee /etc/apt/sources.list.d/cloudflare-workers-proxy.list
sudo apt update && sudo apt install cloudflared -y
```

### Step 3 — Create the tunnel

```bash
cloudflared tunnel login           # opens browser login
cloudflared tunnel create smartbin # note the UUID printed
```

### Step 4 — Configure routing

Copy `.cloudflared/config.yml.example` to `.cloudflared/config.yml` and fill in your UUID:

```yaml
# .cloudflared/config.yml  (DO NOT COMMIT — credentials inside)
tunnel: <YOUR_TUNNEL_UUID>
credentials-file: /home/pi/.cloudflared/<YOUR_TUNNEL_UUID>.json

ingress:
  - hostname: ha.yourdomain.com
    service: http://localhost:8123
  - hostname: api.yourdomain.com
    service: http://localhost:5000
  - hostname: upload.yourdomain.com
    service: http://localhost:5001
  - hostname: asyncapi.yourdomain.com
    service: http://localhost:5002
  - service: http_status:404
```

### Step 5 — Add DNS records

```bash
cloudflared tunnel route dns smartbin ha.yourdomain.com
cloudflared tunnel route dns smartbin api.yourdomain.com
cloudflared tunnel route dns smartbin upload.yourdomain.com
cloudflared tunnel route dns smartbin asyncapi.yourdomain.com
```

### Step 6 — Run as system service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

The tunnel reconnects automatically after Pi reboots.

### What to commit vs what NOT to commit

| File | Commit? | Reason |
|---|---|---|
| `.cloudflared/config.yml.example` | ✅ Yes | Template with placeholders — safe |
| `.cloudflared/config.yml` | ❌ No | Contains tunnel UUID — gitignored |
| `.cloudflared/<UUID>.json` | ❌ No | Tunnel credentials — gitignored |

---

## 15. Configuration Reference

All configurable values and their defaults:

| Parameter | Default | Where |
|---|---|---|
| MQTT broker host | `mosquitto` (Docker) / `localhost` (bare) | `--host` CLI arg |
| MQTT broker port | `1883` | `--port` CLI arg |
| PIR GPIO pin (BCM) | `17` | `--pin` CLI arg |
| Sample interval (s) | `0.1` (10 Hz) | `--sample-interval` |
| Cooldown between events (s) | `5.0` | `--cooldown` |
| Minimum HIGH duration (s) | `0.2` | `--min-high` |
| Bin capacity (disposal events = 100%) | `50` | `BIN_CAPACITY` in `producer.py` |
| Event queue max size | `100` | `--queue-size` |
| Producer run duration (s) | `600` (10 min) | `--duration` |
| Rolling window for rules (min) | `10` | `--window` in `virtual_sensor_rules.py` |
| Rules evaluation interval (s) | `30` | `--interval` |
| ML prediction interval (s) | `60` | `--interval` in `virtual_sensor_ml.py` |
| Fill alert threshold (%) | `80` | Node-RED switch node |
| MQTT broker env (api) | `MQTT_BROKER=mosquitto` | `docker-compose.yml` environment |

---

## 16. Extending the System

### Add a second bin

1. Start a second producer with `--bin-id bin-02 --sensor-id pir-02 --pin 27`
2. Add a second entry in the Node-RED MQTT subscribe nodes using `bin-02`
3. Add a second `wastebin.jsonld` and `sensor.jsonld` under `models/`
4. The API's `_build_registries()` currently reads a single file — extend it to glob all `wastebin-*.jsonld` files

### Add a new sensor type (e.g. ultrasonic fill sensor)

1. Create `src/pirlib/ultrasonic_sampler.py` following the `PirSampler` interface (`.read()` → bool/float)
2. Add a new topic `smartbin/{bin_id}/fill-distance/state`
3. Cross-validate against the PIR-derived fill level in a new virtual sensor

### Add a new API endpoint

```python
# In api.py, add under the /bins namespace:
@ns.route("/<string:bin_id>/your-new-endpoint")
class YourEndpoint(Resource):
    def get(self, bin_id):
        """Your description shown in Swagger."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin '{bin_id}' not found")
        # query DB or MQTT store
        return {"result": "..."}, 200
```

### Add a new Node-RED flow

1. Edit in the UI at `http://localhost:1880`
2. Deploy
3. Export via Hamburger → Export → All flows → JSON
4. Overwrite `node-red/flows.json` and commit

### Multi-Pi deployment

Each Pi runs its own producer with a unique `--bin-id`. Point all producers at a shared
Mosquitto broker IP. The consumer, API, and Node-RED can run on a central server,
subscribing to `smartbin/#` to receive events from all bins.

---

## 17. Troubleshooting

### Producer fails with `lgpio` error

```
lgpio.error: can't connect to pigpio
```

This is expected on non-Pi hardware. The `PirSampler` automatically stubs out GPIO.
No action needed — events simply won't be generated from hardware.

### MQTT connection refused on startup

Services start in parallel. The producer/consumer retry automatically
(`reconnect_delay_set(min_delay=1, max_delay=30)`).
If the error persists after 30 seconds:

```bash
docker compose logs mosquitto
docker compose restart mosquitto
```

### Node-RED sqlite node missing

```bash
docker exec -it smartbin-node-red-1 \
  npm install --prefix /usr/src/node-red node-red-node-sqlite
docker compose restart node-red
```

### Database file not created

The `smartbin.db` is created by `api.py` on first start. Check:

```bash
docker compose logs api | grep -i "sqlite\|db\|database"
docker exec -it smartbin-api-1 ls /app/data/
```

### Cloudflare tunnel shows "Offline"

```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 50
# Most common fix:
cloudflared tunnel login   # re-authenticate
sudo systemctl restart cloudflared
```

### ML model file not found

The model is baked into the Docker image at build time via `RUN python train_model.py`.
If the `models_v_s/` volume mount overrides the baked model with an empty directory:

```bash
ls ./models_v_s/
# If empty, run:
docker compose run --rm virtual_sensor_ml python train_model.py
```

---

## License

MIT — see `LICENSE` file.

## Team

Team 08 · Internet of Things Lab · 2025–2026
