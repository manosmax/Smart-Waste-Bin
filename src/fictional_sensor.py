import argparse
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

BIN_CAPACITY = 50

JSONLD_CONTEXT = {
    "@vocab":   "https://schema.org/",
    "sosa":     "http://www.w3.org/ns/sosa/",
    "ssn":      "http://www.w3.org/ns/ssn/",
    "xsd":      "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Smart-Waste-Bin/blob/main/docs/Ontology.md#",
    "event_time":          {"@id": "sosa:resultTime",         "@type": "xsd:dateTime"},
    "ingest_time":         {"@id": "pipeline:ingestTime",     "@type": "xsd:dateTime"},
    "device_id":           {"@id": "sosa:madeBySensor",       "@type": "@id"},
    "mounted_on":          {"@id": "sosa:isHostedBy",         "@type": "@id"},
    "event_type":          {"@id": "sosa:observedProperty",   "@type": "@id"},
    "motion_state":        {"@id": "sosa:hasSimpleResult",    "@type": "xsd:string"},
    "seq":                 {"@id": "pipeline:sequenceNumber", "@type": "xsd:integer"},
    "run_id":              {"@id": "pipeline:runId",          "@type": "xsd:string"},
    "pipeline_latency_ms": {"@id": "pipeline:latencyMs",      "@type": "xsd:decimal"},
    "item_count":          {"@id": "pipeline:itemCount",      "@type": "xsd:integer"},
    "fill_level":          {"@id": "pipeline:fillLevel",      "@type": "xsd:integer"},
}


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fictional PIR sensor — publishes simulated events to MQTT")
    p.add_argument("--bin-id",       default="bin-02")
    p.add_argument("--sensor-id",    default="pir-02")
    p.add_argument("--device-id",    default="urn:dev:team08:pir-02")
    p.add_argument("--host",         default="localhost")
    p.add_argument("--port",         type=int,   default=1883)
    p.add_argument("--qos",          type=int,   default=1)
    p.add_argument("--topic",        default="smartbin/bin-02/pir-02/events")
    p.add_argument("--min-interval", type=float, default=3.0,
                   help="Minimum seconds between generated events")
    p.add_argument("--max-interval", type=float, default=30.0,
                   help="Maximum seconds between generated events (quiet hours)")
    p.add_argument("--busy-hours",   default="8,9,10,11,12,13,14,15,17",
                   help="Comma-separated hours with higher activity (shorter intervals)")
    p.add_argument("--duration",     type=float, default=7200.0,
                   help="Total run duration in seconds. 0 = run forever.")
    p.add_argument("--verbose",      action="store_true")
    return p.parse_args()



def send_discovery(client, bin_id: str, sensor_id: str,
                   pir_topic: str, fill_topic: str, qos: int) -> None:
    """Publish retained HA MQTT Discovery payloads for bin-02."""
    device_info = {
        "identifiers":  [bin_id],
        "name":         f"Smart Waste Bin {bin_id} (virtual)",
        "model":        "IoT-Bin-v2-virtual",
        "manufacturer": "Team 08",
    }

    pir_config = {
        "name":          f"Waste Bin {bin_id} Motion",
        "state_topic":   pir_topic,
        "payload_on":    "detected",
        "payload_off":   "clear",
        "device_class":  "motion",
        "unique_id":     f"{bin_id}_{sensor_id}_motion",
        "off_delay":     6,
        "device":        device_info,
    }

    fill_config = {
        "name":               f"Waste Bin {bin_id} Fill Level",
        "state_topic":        fill_topic,
        "unit_of_measurement": "%",
        "icon":               "mdi:delete-variant",
        "state_class":        "measurement",
        "unique_id":          f"{bin_id}_fill_level",
        "device":             device_info,
    }

    client.publish(
        f"homeassistant/binary_sensor/{bin_id}_{sensor_id}/config",
        json.dumps(pir_config), qos=qos, retain=True,
    )
    client.publish(
        f"homeassistant/sensor/{bin_id}_fill/config",
        json.dumps(fill_config), qos=qos, retain=True,
    )
    logger.info("[HA] Discovery sent for %s / %s", bin_id, sensor_id)



def get_interval(busy_hours: set, min_iv: float, max_iv: float) -> float:
    import random
    current_hour = datetime.now().hour
    if current_hour in busy_hours:
        return random.uniform(min_iv, min_iv * 4)
    return random.uniform(min_iv * 4, max_iv)



def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    busy_hours = {int(h.strip()) for h in args.busy_hours.split(",") if h.strip()}

    topic        = args.topic
    qos          = args.qos
    ha_pir_topic = f"smartbin/{args.bin_id}/{args.sensor_id}/motion"
    ha_fill_topic= f"smartbin/{args.bin_id}/fill-level/state"
    cmd_topic    = f"smartbin/{args.bin_id}/command"

    run_id     = str(uuid.uuid4())
    seq        = 0
    item_count = 0
    fill_level = 0
    connected  = {"ok": False}

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, f"fictional-sensor-{args.bin_id}")

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            connected["ok"] = True
            logger.info("[MQTT] Connected to broker at %s:%s", args.host, args.port)

            # Send HA discovery immediately on connect
            send_discovery(c, args.bin_id, args.sensor_id,
                           ha_pir_topic, ha_fill_topic, qos)

            # Publish online status
            c.publish(f"{topic}/status", "online", qos=qos, retain=True)

            # Subscribe to command topic (e.g. emptied command from api.py)
            c.subscribe(cmd_topic, qos=qos)
            logger.info("[MQTT] Subscribed to %s", cmd_topic)
        else:
            logger.error("[MQTT] Connection failed rc=%s", reason_code)

    def on_message(c, userdata, msg):
        nonlocal item_count, fill_level
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return

        if payload.get("action") == "emptied":
            item_count = 0
            fill_level = 0
            c.publish(ha_fill_topic, "0", qos=qos, retain=True)
            logger.info("[CMD] Bin %s emptied via command topic.", args.bin_id)

    def on_disconnect(c, userdata, disconnect_flags, reason_code, properties):
        connected["ok"] = False
        if reason_code != 0:
            logger.warning("[MQTT] Unexpected disconnect rc=%s — will auto-reconnect.", reason_code)

    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    client.will_set(f"{topic}/status", "offline", qos=qos, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(args.host, args.port, keepalive=60)
    except Exception as exc:
        logger.error("[MQTT] Could not connect: %s", exc)
        return

    client.loop_start()

    timeout = time.monotonic() + 10
    while not connected["ok"] and time.monotonic() < timeout:
        time.sleep(0.1)

    if not connected["ok"]:
        logger.error("[MQTT] Timed out waiting for broker connection. Exiting.")
        client.loop_stop()
        return

    logger.info(
        "[FICTIONAL] Starting — bin=%s sensor=%s duration=%.0fs busy_hours=%s",
        args.bin_id, args.sensor_id, args.duration, sorted(busy_hours),
    )

    start_t    = time.time()
    run_forever = args.duration == 0

    try:
        while run_forever or (time.time() - start_t) < args.duration:

            interval = get_interval(busy_hours, args.min_interval, args.max_interval)
            time.sleep(interval)

            if not (run_forever or (time.time() - start_t) < args.duration):
                break

            seq        += 1
            item_count += 1
            fill_level  = min(int((item_count / BIN_CAPACITY) * 100), 100)

            record = {
                "@context":    JSONLD_CONTEXT,
                "@id":         f"urn:event:{run_id}:{seq}",
                "@type":       "sosa:Observation",
                "event_time":  utc_now_iso(),
                "device_id":   args.device_id,
                "event_type":  "urn:prop:team08:motion",
                "motion_state":"detected",
                "seq":         seq,
                "run_id":      run_id,
                "mounted_on":  f"urn:wastebin:{args.bin_id}",
                "item_count":  item_count,
                "fill_level":  fill_level,
            }

            # 1. Full JSON-LD event → main topic (consumed by api.py → PIR_Events)
            client.publish(topic, json.dumps(record, default=str), qos=qos)

            # 2. HA motion state → binary_sensor
            client.publish(ha_pir_topic, "detected", qos=qos)

            # 3. HA fill level → sensor
            client.publish(ha_fill_topic, str(fill_level), qos=qos)

            if args.verbose:
                logger.debug(
                    "[FICTIONAL] seq=%d  fill=%d%%  interval=%.1fs",
                    seq, fill_level, interval,
                )
            else:
                logger.info(
                    "[FICTIONAL] Event published — seq=%d  fill=%d%%  next in ~%.0fs",
                    seq, fill_level, interval,
                )

    except KeyboardInterrupt:
        logger.info("\n[FICTIONAL] Ctrl-C — stopping.")
    finally:
        client.publish(f"{topic}/status", "offline", qos=qos, retain=True).wait_for_publish(3.0)
        client.loop_stop()
        client.disconnect()

    logger.info("[FICTIONAL] Done. Total events published: %d", seq)


if __name__ == "__main__":
    main()