import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from pirlib import PirInterpreter, PirSampler

from consumer import consumer_loop 
from producer import producer_loop

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))





def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR motion event pipeline")

    p.add_argument("--device-id",        default="pir-01",
                   help="Logical name for this sensor device")
    p.add_argument("--pin",              type=int,   default=18,
                   help="BCM GPIO pin number the PIR is wired to")
    p.add_argument("--sample-interval",  type=float, default=0.1,
                   help="Seconds between PIR reads (e.g. 0.1 = 10 Hz)")
    p.add_argument("--cooldown",         type=float, default=5.0,
                   help="Minimum seconds between emitted events (interpreter cooldown)")
    p.add_argument("--min-high",         type=float, default=0.2,
                   help="Minimum seconds the signal must stay HIGH before emitting")
    p.add_argument("--queue-size",       type=int,   default=100,
                   help="Maximum number of records the bounded queue can hold")
    p.add_argument("--consumer-delay",   type=float, default=0.0,
                   help="Artificial delay (s) added per record in the consumer "
                        "(simulate slow downstream)")
    p.add_argument("--duration",         type=float, default=60.0,
                   help="How long (seconds) to run the pipeline before stopping")
    p.add_argument("--out",              default="motion_pipeline.jsonl",
                   help="Path to the JSONL output file")
    p.add_argument("--verbose",          action="store_true",
                   help="Print periodic status lines to stdout")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics = {
        "produced":  0,
        "consumed":  0,
        "dropped":   0,
        "max_queue": 0,
    }
    stop_flag = {"stop": False}

    
    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(
        cooldown_s=args.cooldown,
        min_high_s=args.min_high,
    )

    
    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, metrics, stop_flag),
        daemon=True,
    )

    consumer_t = threading.Thread(
        target=consumer_loop,
        args=(event_q, args.out, args, metrics, stop_flag),
        daemon=True,
    )

    print(f"[main] Starting pipeline  device={args.device_id}  pin={args.pin}  "
          f"duration={args.duration}s  out={args.out}")

    producer_t.start()
    consumer_t.start()

    start_t = time.time()
    try:
        while (time.time() - start_t) < args.duration:
            if args.verbose:
                print(
                    f"[status] produced={metrics['produced']} "
                    f"consumed={metrics['consumed']} "
                    f"dropped={metrics['dropped']} "
                    f"queue={event_q.qsize()} "
                    f"max_queue={metrics['max_queue']}"
                )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[main] Ctrl-C received — stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        consumer_t.join()
        sampler.cleanup()

    print(
        f"[main] Done.  produced={metrics['produced']}  "
        f"consumed={metrics['consumed']}  dropped={metrics['dropped']}  "
        f"max_queue={metrics['max_queue']}"
    )


if __name__ == "__main__":
    main()