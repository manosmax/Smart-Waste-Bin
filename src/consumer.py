import argparse
import json
import time
from queue import Empty, Queue
from run_pipeline import utc_now_iso , parse_iso_utc

def consumer_loop(
    event_q: Queue,
    out_path: str,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    """
    Dequeues event records, enriches them with ingest_time and
    pipeline_latency_ms, then writes one JSON object per line to the
    output file.
    """
    with open(out_path, "a", encoding="utf-8") as f:
        while not stop_flag["stop"] or not event_q.empty():
            try:
                record = event_q.get(timeout=0.5)
            except Empty:
                continue

            # Enrich the record
            ingest_ts = utc_now_iso()
            record["ingest_time"] = ingest_ts

            event_dt  = parse_iso_utc(record["event_time"])
            ingest_dt = parse_iso_utc(ingest_ts)
            latency_ms = (ingest_dt - event_dt).total_seconds() * 1000.0
            record["pipeline_latency_ms"] = round(latency_ms, 3)

            # Write one JSON line and flush immediately
            f.write(json.dumps(record) + "\n")
            f.flush()

            metrics["consumed"] += 1
            metrics["max_queue"] = max(metrics["max_queue"], event_q.qsize())
            event_q.task_done()

            if args.consumer_delay > 0.0:
                time.sleep(args.consumer_delay)
