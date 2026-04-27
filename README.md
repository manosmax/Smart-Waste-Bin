#  Smart-Waste-Bin 
### Team 8 — Lab Repository
*Electrical & Computer Engineering · University of Patras*

---

## 👥 Team Members
| # | Name | Student ID |
|---|------|-----------|
| 1 | Anastasios Kanellopoulos | `1100882` |
| 2 | Pasamihalis Emmanouil | `1101001` |
| 3 | Giakoumakis Emmanouil | `1100838` |

---

## Overview

A smart waste bin system that uses a PIR motion sensor on a Raspberry Pi to detect when someone approaches the bin. Events are published over MQTT and consumed by a subscriber that logs them to a JSONL file. The whole stack runs in Docker.

---

## Project Structure

```
Smart-Waste-Bin/
├── src/
│   ├── producer.py       # Reads PIR sensor, publishes events to MQTT
│   ├── consumer.py       # Subscribes to MQTT, writes events to JSONL
│   └── pirlib/           # PIR sensor driver (sampler + interpreter)
├── docs/                 # Ontology and JSON-LD models
├── models/               # context.jsonld, sensor.jsonld, wastebin.jsonld
├── Dockerfile
├── docker-compose.yml
├── mosquitto.conf
└── requirements.txt
```

---

## Wiring *(Raspberry Pi)*

| Sensor Pin | Pi Physical Pin | BCM Name |
|------------|-----------------|----------|
| `VCC`      | 2               | 5V       |
| `GND`      | 6               | GND      |
| `OUT`      | 11              | GPIO17   |

---

## Build 
```bash 
docker compose build
``` 

## Run with Docker
```bash
# Terminal 1 — MQTT broker
docker compose up mosquitto

# Terminal 2 — PIR producer
docker compose up producer

# Terminal 3 — MQTT consumer
docker compose up consumer
```

Events are saved to `data/motion_events.jsonl`.

``` Bash 
# In order to view the jsonl output with a preetier format run : 
while IFS= read -r line; do echo "$line" | python -m json.tool; echo "---"; done < data/motion_events.jsonl
``` 


To pass custom arguments, override the command in `docker-compose.yml`:

```yaml
producer:
  command: python -u producer.py --verbose --pin 17 --cooldown 2.0 --min-high 0.1
consumer:
  command: python -u consumer.py --verbose --out /app/data/motion_events.jsonl
```

Or run directly without Docker:

```bash
python -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt

systemctl start mosquitto 

python src/producer.py --pin 17 --cooldown 2.0 --min-high 0.1 --verbose
python src/consumer.py --out data/motion_events.jsonl --verbose
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--pin` | `17` | GPIO BCM pin number |
| `--cooldown` | `5.0` | Seconds between events |
| `--min-high` | `0.2` | Seconds signal must stay HIGH |
| `--duration` | `600.0` | How long to run (seconds) |
| `--host` | `localhost` | MQTT broker host |
| `--port` | `1883` | MQTT broker port |
| `--topic` | `smartbin/bin-01/pir-01/events` | MQTT topic |
| `--qos` | `1` | MQTT QoS level |
| `--out` | `motion_pipeline.jsonl` | Output file (consumer only) |
| `--verbose` | `false` | Print live status |

---

*Made with ❤️ by Team 8 · ECE Upatras*
