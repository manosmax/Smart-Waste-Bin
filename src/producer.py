import argparse
import time
import uuid
from queue import Full, Queue
from pirlib import PirInterpreter, PirSampler
from run_pipeline import utc_now_iso



def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    """
    Reads PIR samples, passes them through the interpreter, and enqueues
    structured event records.  Drops the newest record when the queue is full
    """
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _event in interp.update(raw, t):
            seq += 1

            record = {
                "event_time":   utc_now_iso(),
                "device_id":    args.device_id,
                "event_type":   "motion",
                "motion_state": "detected",
                "seq":          seq,
                "run_id":       run_id,
            }

            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1

        time.sleep(args.sample_interval)
