#!/usr/bin/env python3
"""Live RD-03D radar monitor -> terminal. No GUI, no pondeyes.db writes.

Usage:
  python3 radar_monitor.py            # live, refreshes in place (Ctrl-C to quit)
  python3 radar_monitor.py --seconds 8
  python3 radar_monitor.py --plain    # one line per update (good for logs/pipes)
"""
import sys
import time
import math
import json
import argparse
import serial
from radar import frames   # reuse the project wire-format (HDR/FTR/FLEN/s15)

PORT, BAUD = "/dev/serial0", 256000
CMD = bytes.fromhex("fdfcfbfa0200900004030201")  # enter multi-target mode

CLEAR = "\x1b[H\x1b[2J"
SHOW_CURSOR = "\x1b[?25h"
HEADER = "  slot     x(mm)    y(mm)    speed    range   bearing"


def decode(frame):
    """Return list of dicts with x, y, speed (mm/s), range (mm), bearing (deg)."""
    out = []
    for i in range(3):
        off = 4 + i * 8
        x = frames.s15(int.from_bytes(frame[off:off + 2], "little"))
        y = frames.s15(int.from_bytes(frame[off + 2:off + 4], "little"))
        if not (x or y):
            continue
        spd = frames.s15(int.from_bytes(frame[off + 4:off + 6], "little"))
        rng = math.hypot(x, y)
        brg = math.degrees(math.atan2(x, y))   # 0deg = straight ahead, + = right
        out.append({"slot": i + 1, "x": x, "y": y, "spd": spd, "rng": rng, "brg": brg})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0.0, help="run time (0 = forever)")
    ap.add_argument("--plain", action="store_true", help="line-per-update output")
    ap.add_argument("--ndjson", action="store_true",
                    help="emit one JSON object per frame (for the Mac plotter)")
    args = ap.parse_args()
    ndjson = args.ndjson
    live = sys.stdout.isatty() and not args.plain and not ndjson

    def open_serial():
        s = serial.Serial(PORT, BAUD, 8, "N", 1, timeout=0.2)
        s.reset_input_buffer()
        s.write(CMD)            # (re)enter multi-target mode on every (re)open
        s.flush()
        return s

    ser = open_serial()
    if live:
        sys.stdout.write(CLEAR)

    buf = bytearray()
    t0 = time.monotonic()
    last_rx = t0
    nframes = 0
    last_draw = 0.0
    STALL_S = 3.0           # no bytes for this long -> PL011 RX likely wedged; reopen
    try:
        while True:
            if args.seconds and time.monotonic() - t0 >= args.seconds:
                break
            chunk = ser.read(512)
            now_rx = time.monotonic()
            if chunk:
                buf.extend(chunk)
                last_rx = now_rx
            elif now_rx - last_rx > STALL_S:
                # Radar still transmits, but this fd's PL011 RX wedged (cts_event quirk).
                # Close and reopen to recover, re-sending the multi-target command.
                print(f"[monitor] no data for {STALL_S:.0f}s -- reopening {PORT}",
                      file=sys.stderr, flush=True)
                try:
                    ser.close()
                except Exception:
                    pass
                try:
                    ser = open_serial()
                except serial.SerialException as exc:
                    print(f"[monitor] reopen failed: {exc}", file=sys.stderr, flush=True)
                    time.sleep(0.5)
                buf.clear()
                last_rx = time.monotonic()
                continue

            targets = None
            while True:
                j = buf.find(frames.HDR)
                if j < 0 or j + frames.FLEN > len(buf):
                    break
                fr = bytes(buf[j:j + frames.FLEN])
                if fr.endswith(frames.FTR):
                    targets = decode(fr)
                    nframes += 1
                    del buf[:j + frames.FLEN]
                    if ndjson:
                        sys.stdout.write(
                            json.dumps({"f": nframes, "targets": targets}) + "\n")
                        sys.stdout.flush()
                else:
                    del buf[:j + 1]

            if ndjson or targets is None:
                continue
            now = time.monotonic()
            if now - last_draw < 0.1:   # cap redraw ~10 Hz
                continue
            last_draw = now
            fps = nframes / max(now - t0, 1e-3)

            if live:
                lines = [
                    CLEAR,
                    f"  RD-03D live  /dev/serial0 @ {BAUD}   "
                    f"frames={nframes}  ~{fps:4.1f} fps   (Ctrl-C to quit)",
                    "  " + "-" * 56,
                    HEADER,
                ]
                if targets:
                    for t in targets:
                        lines.append(
                            f"  {t['slot']:>4} {t['x']:>8d} {t['y']:>8d} "
                            f"{t['spd']:>6d}mm/s {t['rng']:>6.0f}mm {t['brg']:>+7.1f}deg"
                        )
                else:
                    lines.append("  (no target in view)")
                sys.stdout.write("\n".join(lines) + "\n")
                sys.stdout.flush()
            else:
                ts = now - t0
                if targets:
                    s = "  ".join(
                        f"T{t['slot']}: x={t['x']:+5d} y={t['y']:+5d} "
                        f"v={t['spd']:+4d} r={t['rng']:4.0f} b={t['brg']:+6.1f}deg"
                        for t in targets
                    )
                else:
                    s = "(no target)"
                print(f"t={ts:5.1f}s f={nframes:<5d} {s}")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        if live:
            sys.stdout.write(SHOW_CURSOR)
        print(f"\nstopped after {nframes} frames in {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
