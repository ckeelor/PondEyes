# tools/sim_sensor.py
# ===================
#
# Hardware-free MQTT sensor simulator. Publishes well-formed LD2450 frames (built with the
# SAME encoder the app parses, radar.frames.build_frame) to an MQTT topic, following one of
# the shared trajectories. Run two of these on different topics to exercise the full
# multi-sensor pipeline end-to-end over a real broker, with no radios.
#
# Usage:
#   .venv/bin/python tools/sim_sensor.py --topic PondEyes/raw_S2 --pattern circle
#   .venv/bin/python tools/sim_sensor.py --topic PondEyes/raw_S3 --pattern line --hz 15
#
# Then point a sensor's input_mode at "mqtt" with the matching topic (or just use the app's
# built-in input_mode "sim", which needs no broker at all — this tool is for testing the real
# MQTT transport specifically).

from __future__ import annotations

import argparse
import time
from pathlib import Path

# Make `radar` importable when run from the project root.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt           # noqa: E402
from radar import frames, trajectories    # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Publish synthetic LD2450 frames to MQTT.")
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--pattern", default="circle",
                    help="static | line | circle | random_walk")
    ap.add_argument("--hz", type=float, default=10.0, help="frames per second")
    args = ap.parse_args()

    traj = trajectories.make(args.pattern)
    cli = mqtt.Client()
    cli.connect(args.broker, args.port, 60)
    cli.loop_start()

    period = 1.0 / args.hz if args.hz > 0 else 0.1
    print(f"[sim] publishing {args.pattern} frames to {args.topic} @ {args.hz} Hz "
          f"(Ctrl-C to stop)")
    t = 0.0
    try:
        while True:
            # Build a real 30-byte frame from the trajectory and publish it as a hex string,
            # exactly the payload format RadarMQTT expects.
            frame = frames.build_frame(traj(t))
            cli.publish(args.topic, frame.hex())
            t += period
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n[sim] stopped.")
    finally:
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
