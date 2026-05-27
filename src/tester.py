"""
read_sensor.py — Continuous raw PIR sensor reader using lgpio (matches pirlib/PirSampler).
Prints the sensor state on every poll interval.

Usage:
    python read_sensor.py
    python read_sensor.py --pin 17 --interval 0.1
"""

import argparse
import time
from datetime import datetime

try:
    import lgpio
    handle = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_input(handle, 17)  # claimed temporarily, overridden in main
    GPIO_OK = True
except Exception as e:
    print(f"[WARN] lgpio not available ({e}) — running in mock mode.")
    lgpio  = None
    GPIO_OK = False


def parse_args():
    p = argparse.ArgumentParser(description="Continuous raw PIR sensor reader (lgpio)")
    p.add_argument("--pin",      type=int,   default=17,  help="BCM GPIO pin number")
    p.add_argument("--interval", type=float, default=0.1, help="Poll interval in seconds")
    return p.parse_args()


def main():
    args = parse_args()

    if GPIO_OK:
        # Re-claim the correct pin from args (releases the temp claim above)
        try:
            lgpio.gpio_free(handle, 17)
        except Exception:
            pass
        lgpio.gpio_claim_input(handle, args.pin)
        read = lambda: bool(lgpio.gpio_read(handle, args.pin))
        print(f"[INFO] lgpio — reading BCM {args.pin} every {args.interval}s — Ctrl-C to stop.\n")
    else:
        import random
        read = lambda: random.choices([0, 1], weights=[85, 15])[0]
        print(f"[INFO] Mock mode — simulating BCM {args.pin} — Ctrl-C to stop.\n")

    print(f"{'Timestamp':<28} {'Pin':<6} {'Raw':<6} {'State'}")
    print("-" * 60)

    try:
        while True:
            state = read()
            now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            label = "HIGH  ← MOTION DETECTED" if state else "LOW   — no motion"
            print(f"{now:<28} {args.pin:<6} {int(state):<6} {label}")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")
    finally:
        if GPIO_OK:
            lgpio.gpiochip_close(handle)


if __name__ == "__main__":
    main()