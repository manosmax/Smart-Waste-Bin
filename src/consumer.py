import argparse
import json
import logging
import os
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from database import (
    DB_PATH,
    get_connection,
    init_db,
    insert_mqtt_message,
    insert_pir_event,
    upsert_bin,
    upsert_sensor,
    upsert_mounted_on,
)

logger = logging.getLogger(__name__)

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(_BASE_DIR, "models")



def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def get_dated_path(base_path: str) -> str:
    root, ext = os.path.splitext(base_path)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{root}_{date_str}{ext}"


def append_record(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def extract_bin_id(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] == "smartbin":
        return parts[1]
    return None


def bin_exists(db_conn, db_lock: threading.Lock, bin_id: str | None) -> bool:
    if not bin_id:
        return False
    with db_lock:
        return db_conn.execute(
            "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
        ).fetchone() is not None



def _load_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _uri_to_short_id(uri: str) -> str:
    return uri.split(":")[-1]


def _bootstrap_registries(db_conn, db_lock: threading.Lock) -> None:
    wb  = _load_json_safe(os.path.join(MODELS_DIR, "wastebin.jsonld"))
    s   = _load_json_safe(os.path.join(MODELS_DIR, "sensor.jsonld"))
    env = _load_json_safe(os.path.join(MODELS_DIR, "environment.jsonld"))

    env_name = env.get("name", env.get("@id", "Unknown"))

    bin_nodes = wb.get("@graph", [wb]) if wb else []
    for node in bin_nodes:
        bin_uri = node.get("@id", "")
        if not bin_uri:
            continue
        bin_id   = _uri_to_short_id(bin_uri)
        raw_stat = node.get("pipeline:status", "active")
        status   = raw_stat.get("@value", "active") if isinstance(raw_stat, dict) else raw_stat
        with db_lock:
            upsert_bin(db_conn, bin_id, bin_uri, node.get("name", ""), env_name, status)
        logger.info("[BOOTSTRAP] Upserted bin: %s", bin_id)

    sensor_nodes = s.get("@graph", [s]) if s else []
    for node in sensor_nodes:
        sensor_uri = node.get("@id", "")
        if not sensor_uri:
            continue
        sensor_id   = _uri_to_short_id(sensor_uri)
        mounted_uri = node.get("sosa:isHostedBy", "")
        bin_id_s    = _uri_to_short_id(mounted_uri) if mounted_uri else None
        raw_stat    = node.get("pipeline:status", "active")
        status      = raw_stat.get("@value", "active") if isinstance(raw_stat, dict) else raw_stat

        with db_lock:
            upsert_sensor(db_conn, sensor_id, sensor_uri, "PIR",
                          node.get("model", ""), status)
            logger.info("[BOOTSTRAP] Upserted sensor: %s", sensor_id)

            if bin_id_s:
                exists = db_conn.execute(
                    "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id_s,)
                ).fetchone()
                if exists:
                    upsert_mounted_on(db_conn, sensor_id, bin_id_s)
                    logger.info("[BOOTSTRAP] Mounted %s → %s", sensor_id, bin_id_s)
                else:
                    logger.warning(
                        "[BOOTSTRAP] Skipping mount — bin '%s' not found for sensor '%s'.",
                        bin_id_s, sensor_id
                    )



def make_on_connect(args: argparse.Namespace):
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("[CONSUMER] Connected to broker %s:%s", args.host, args.port)
            client.subscribe(args.topic, qos=1)
            logger.info("[CONSUMER] Subscribed to %s", args.topic)
        else:
            logger.error("[CONSUMER] Connection failed rc=%s", reason_code)
    return on_connect


def make_on_message(args: argparse.Namespace, db_conn, db_lock: threading.Lock):
    def on_message(client, userdata, msg):
        try:
            record = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            logger.warning("[CONSUMER] Bad JSON on %s: %s", msg.topic, exc)
            return

        ingest_ts = utc_now_iso()
        record["ingest_time"] = ingest_ts

        event_ts_str = record.get("event_time")
        if event_ts_str:
            try:
                latency_ms = (
                    parse_iso(ingest_ts) - parse_iso(event_ts_str)
                ).total_seconds() * 1000.0
                record["pipeline_latency_ms"] = round(latency_ms, 3)
            except Exception as exc:
                logger.debug("[CONSUMER] Could not compute latency: %s", exc)

        enriched_payload = json.dumps(record)
        topic_bin_id     = extract_bin_id(msg.topic)

        safe_bin_id = topic_bin_id if bin_exists(db_conn, db_lock, topic_bin_id) else None
        if topic_bin_id and safe_bin_id is None:
            logger.warning(
                "[CONSUMER] Unknown bin_id '%s' on topic %s — storing without FK link",
                topic_bin_id, msg.topic,
            )

        with db_lock:
            insert_mqtt_message(
                db_conn, msg.topic, enriched_payload,
                msg.qos, msg.retain, safe_bin_id,
            )

        if "/events" in msg.topic:
            parts = msg.topic.split("/")  # ["smartbin", "bin-02", "pir-02", "events"]
            event_bin_id    = parts[1] if len(parts) > 1 else topic_bin_id
            event_sensor_id = parts[2] if len(parts) > 2 else None

            record["bin_id"]    = event_bin_id
            record["sensor_id"] = event_sensor_id

            if event_bin_id and bin_exists(db_conn, db_lock, event_bin_id):
                with db_lock:
                    insert_pir_event(db_conn, record)
            else:
                logger.warning(
                    "[CONSUMER] Skipping PIR_Events insert — unknown bin_id '%s'",
                    event_bin_id,
                )

        append_record(args.out, record)
        append_record(get_dated_path(args.out), record)

        if args.verbose:
            logger.debug(
                "[CONSUMER] seq=%-4s  latency=%.1fms  fill=%s%%  bin=%s",
                record.get("seq", "?"),
                record.get("pipeline_latency_ms", float("nan")),
                record.get("fill_level", "?"),
                record.get("bin_id") or safe_bin_id or "?",
            )

    return on_message



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Wastebin MQTT Consumer — enriches events, writes DB + JSONL"
    )
    parser.add_argument("--host",    default="localhost")
    parser.add_argument("--port",    type=int, default=1883)
    parser.add_argument("--topic",   default="smartbin/#")
    parser.add_argument("--out",     default="/app/data/motion_events.jsonl")
    parser.add_argument("--db",      default=DB_PATH)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_db(args.db)
    db_conn = get_connection(args.db)
    db_lock = threading.Lock()
    logger.info("[CONSUMER] DB      : %s", args.db)
    logger.info("[CONSUMER] Master  : %s", args.out)
    logger.info("[CONSUMER] Dated   : %s", get_dated_path(args.out))

    _bootstrap_registries(db_conn, db_lock)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-consumer")
    client.on_connect = make_on_connect(args)
    client.on_message = make_on_message(args, db_conn, db_lock)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.host, args.port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("\n[CONSUMER] Shutting down.")
        client.disconnect()
        db_conn.close()


if __name__ == "__main__":
    main()
