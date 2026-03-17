<div align="center">

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





*Made with ❤️ by Team 8 · ECE Upatras*

</div>


## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 + |
| RPi.GPIO | 0.7 +|
---

## Project Structure

```
Smart-Waste-Bin-Project/
├── README.md                    # Project documentation
├── requirements.txt             # Python dependencies
├── setup.py                     # Package configuration
├── .gitignore                   # Git ignore rules
└── src/
    └── pirlib/
        ├── __init__.py
        ├── sampler.py           # GPIO abstraction layer
        ├── interpreter.py       # Motion event detector
        └── config.py            # Configuration constants
```


## 1 — Create and activate a virtual environment

```bash
# create
python3 -m venv .venv --system-site-packages

# activate — Linux / macOS
source .venv/bin/activate

# activate — Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

---

## 2 — Install dependencies

**On a Raspberry Pi** (real hardware):

```bash
pip install --upgrade pip
pip install -r requirements.txt
```


---

## 3 — Wire the sensor *(Raspberry Pi only)*

| Sensor Pin | Pi pin (physical) | Pi name (BCM)   | Why |
|------------|-------------------|-----------------|-----|
| `VCC`        | 2                 | 5V|power|
| `GND`        | 6                 | GND|reference|
| `OUT`        | 11                | GPIO17|input signal|

---





## 4 — Run the logger

### Minimal (uses all defaults)

```bash
python pir_event_logger.py --device-id pir-01 --pin 18
```

### Full example

```bash
python pir_event_logger.py \
  --device-id      pir-01              \
  --pin            18                  \
  --sample-interval 0.1               \
  --cooldown       5                   \
  --min-high       0.2                 \
  --duration       60                  \
  --out            motion_events.jsonl \
  --verbose
```

### All CLI flags

| Flag | Type | Default | Description |
|---|---|---|---|
| `--device-id` | str | *(required)* | Identifier embedded in every record |
| `--pin` | int | `18` | BCM GPIO pin number |
| `--sample-interval` | float | `0.1` | Seconds between sensor reads |
| `--cooldown` | float | `5.0` | Min seconds between emitted events |
| `--min-high` | float | `0.0` | Min seconds signal must stay HIGH to count |
| `--duration` | float | `30.0` | Total run time in seconds (`0` = run until Ctrl-C) |
| `--out` | str | `motion_events.jsonl` | Output file (append-only) |
| `--verbose` / `-v` | flag | off | Print each event to stdout |





### Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean stop (duration elapsed or Ctrl-C) |
| `1` | Runtime error (GPIO init failed, file I/O error) |
| `2` | Usage error (bad argument value) |

---

## 5 — Output format

Events are written one JSON object per line (JSONL / ndjson), appended to
`--out`. The file is flushed after every write so partial runs are never lost.

**Example record (pretty-printed):**

```json
{
  "seq":               1,
  "run_id":            "cd2bbc20-f0a0-4e79-ae52-2192978d78b1",
  "device_id":         "pir-01",
  "event_type":        "motion",
  "motion_state":      "detected",
  "event_time":        "2026-03-06T11:51:23.060Z",
  "ingest_time":       "2026-03-06T11:51:23.061Z",
  "latency_ms":        0.12,
  "pin":               18,
  "sample_interval_s": 0.1,
  "cooldown_s":        5.0,
  "min_high_s":        0.2
}
```

**Field reference:**

| Field | Description |
|---|---|
| `seq` | Per-run sequence number, starting at 1 |
| `run_id` | UUID4 unique to this invocation |
| `device_id` | Value of `--device-id` |
| `event_type` | Always `"motion"` |
| `motion_state` | Always `"detected"` |
| `event_time` | UTC ISO-8601 — when the motion was detected |
| `ingest_time` | UTC ISO-8601 — when the record was written |
| `latency_ms` | `ingest_time − event_time` in milliseconds |
| `pin` | BCM pin used |
| `sample_interval_s` | Configured sample interval |
| `cooldown_s` | Configured cooldown |
| `min_high_s` | Configured min-high filter |

---


## 6 — Anti-spam / filtering techniques

The `PirInterpreter` inside `pirlib/interpreter.py` applies five techniques
on every raw sample before an event is ever written to disk:

| # | Technique | CLI flag | What it does |
|---|---|---|---|
| E.2.1 | Sampling rate | `--sample-interval` | Controls how often the pin is read. Too slow → miss short pulses; too fast → CPU waste and noise. |
| E.2.2 | once-per-high | *(always on)* | Emits **exactly one** event per HIGH window, no matter how long the signal stays HIGH. |
| E.2.3 | Cooldown | `--cooldown` | After an event is emitted, ignores new detections for this many seconds. Mirrors the PIR hardware reset (~5–6 s). |
| E.2.4 | min-high filter | `--min-high` | Discards spikes shorter than this duration. Filters sensor warm-up glitches. |
| E.2.5 | Dual timestamps | *(always on)* | Every record stores both `event_time` and `ingest_time`; `latency_ms` is computed automatically. |

---


## 7 — Deactivate the virtual environment

```bash
deactivate
```


