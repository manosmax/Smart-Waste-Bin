import argparse
import json
import logging
import os
from datetime import datetime, timezone


import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)



# Helpers


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )



def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def get_dated_path(base_path: str) -> str:
    """Derive a dated sibling file from the base output path.

    e.g. /app/data/motion_events.jsonl
      -> /app/data/motion_events_2026-05-31.jsonl
    """
    root, ext = os.path.splitext(base_path)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{root}_{date_str}{ext}"


def append_record(path: str, record: dict) -> None:
    """Ensure directory exists and append one JSON line to path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")



def make_on_connect(args: argparse.Namespace):
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("[CONSUMER] Connected to broker %s:%s", args.host, args.port)
            client.subscribe(args.topic, qos=1)
            logger.info("[CONSUMER] Subscribed to %s", args.topic)
        else:
            logger.error("[CONSUMER] Connection failed rc=%s", reason_code)
    return on_connect



def make_on_message(args: argparse.Namespace):
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
                event_dt  = parse_iso(event_ts_str)
                ingest_dt = parse_iso(ingest_ts)
                latency_ms = (ingest_dt - event_dt).total_seconds() * 1000.0
                record["pipeline_latency_ms"] = round(latency_ms, 3)
            except Exception as exc:
                logger.debug("[CONSUMER] Could not compute latency: %s", exc)

        # --- Write 1: rolling master file (always appended) ---
        append_record(args.out, record)

        # --- Write 2: daily rotated file (auto-named by UTC date) ---
        dated_path = get_dated_path(args.out)
        append_record(dated_path, record)

        if args.verbose:
            logger.debug(
                "[CONSUMER] seq=%-4s  latency=%.1f ms  fill=%s%%  files=[%s, %s]",
                record.get("seq", "?"),
                record.get("pipeline_latency_ms", float("nan")),
                record.get("fill_level", "?"),
                os.path.basename(args.out),
                os.path.basename(dated_path),
            )

    return on_message




def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Wastebin MQTT Consumer — subscribes to events, writes JSONL"
    )
    parser.add_argument("--host",    default="localhost",
                        help="MQTT broker hostname (default: localhost)")
    parser.add_argument("--port",    type=int, default=1883,
                        help="MQTT broker port (default: 1883)")
    parser.add_argument("--topic",   default="smartbin/bin-01/pir-01/events",
                        help="Topic to subscribe to")
    parser.add_argument("--out",     default="/app/data/motion_events.jsonl",
                        help="Output JSONL file path (a dated copy is also written automatically)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-consumer")
    client.on_connect = make_on_connect(args)
    client.on_message = make_on_message(args)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.host, args.port, keepalive=60)

    dated_path = get_dated_path(args.out)
    logger.info("[CONSUMER] Writing to master : %s", args.out)
    logger.info("[CONSUMER] Writing to dated  : %s", dated_path)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("\n[CONSUMER] Shutting down.")
        client.disconnect()



if __name__ == "__main__":
    main()
