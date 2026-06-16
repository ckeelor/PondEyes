#!/usr/bin/env python3
"""Live radar scatter plot on the Mac, fed by the Pi's RD-03D over SSH.

Runs `ssh <host> ... radar_monitor.py --ndjson` as a subprocess, reads one JSON
object per frame, and plots targets as a top-down scatter. Each point fades to
transparent over a decay window set by a slider (0..10 s); points older than the
window are dropped.

  python3 radar_plot.py                 # defaults: host=zero2w4, 5 s window
  python3 radar_plot.py --host zero2w4 --window 3
"""
import sys
import json
import time
import threading
import argparse
import subprocess
from collections import deque

import numpy as np
import matplotlib
# Pin an interactive GUI backend explicitly: the framework Python defaults to
# "macosx", but fall back to Tk if that ever fails to load.
try:
    matplotlib.use("macosx")
except Exception:
    matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from matplotlib.animation import FuncAnimation

REMOTE_CMD = (
    "cd ~/PondEyes && . venv/bin/activate && "
    "python3 radar_monitor.py --ndjson"
)
# Each stored point: (arrival_time, x_mm, y_mm, slot). Mac stamps arrival time so
# we never depend on Pi/Mac clock sync. Bounded so a long session can't grow forever.
POINTS = deque(maxlen=20000)
LOCK = threading.Lock()
STOP = threading.Event()
STATS = {"lines": 0}   # raw NDJSON frames received from the stream

# Distinct colour per target slot (1..3).
SLOT_RGB = {
    1: (0.0, 1.0, 0.5),   # green
    2: (0.3, 0.6, 1.0),   # blue
    3: (1.0, 0.5, 0.2),   # orange
}


def reader(proc):
    """Background thread: parse NDJSON from the SSH subprocess into POINTS."""
    for line in proc.stdout:
        if STOP.is_set():
            break
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        now = time.monotonic()
        with LOCK:
            STATS["lines"] += 1
            for t in msg.get("targets", []):
                POINTS.append((now, t["x"], t["y"], t["slot"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="zero2w4", help="ssh host running the radar")
    ap.add_argument("--window", type=float, default=5.0,
                    help="initial decay window seconds (0..10)")
    ap.add_argument("--xlim", type=float, default=3000, help="+/- x extent (mm)")
    ap.add_argument("--ylim", type=float, default=6000, help="max y / range (mm)")
    args = ap.parse_args()

    # Self-heal: a previously hard-killed plot can leave a remote radar_monitor still
    # holding /dev/serial0, which would block this run's monitor from opening the port.
    # Clear any stale one (and give the OS a moment to release the port) before we start.
    # The [r]adar_monitor bracket makes the regex NOT match pkill's own command line
    # (the literal arg contains "[r]adar_..." which the regex won't match), avoiding a
    # self-kill that hangs the ssh call. Cleanup is best-effort: never let it abort launch.
    print(f"[plot] clearing any stale radar_monitor on {args.host} ...", flush=True)
    try:
        subprocess.run(
            ["ssh", args.host, "pkill -f '[r]adar_monitor\\.py' || true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[plot] cleanup skipped ({exc!r}); continuing", flush=True)
    time.sleep(1.0)

    proc = subprocess.Popen(
        ["ssh", args.host, REMOTE_CMD],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
    )
    th = threading.Thread(target=reader, args=(proc,), daemon=True)
    th.start()

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(7, 7))
    fig.subplots_adjust(bottom=0.18)
    ax.set_title(f"RD-03D live — {args.host}")
    ax.set_xlabel("x (mm)   ← left   right →")
    ax.set_ylabel("y / distance from sensor (mm)")
    ax.set_xlim(-args.xlim, args.xlim)
    ax.set_ylim(0, args.ylim)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.2)
    ax.axhline(0, color="gray", lw=0.5)
    ax.axvline(0, color="gray", lw=0.5)
    ax.plot(0, 0, marker="^", color="white", ms=12)   # sensor at origin

    scat = ax.scatter([], [], s=40)
    info = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top",
                   fontsize=9, color="white")

    ax_slider = fig.add_axes([0.15, 0.05, 0.7, 0.03])
    win_slider = Slider(ax_slider, "decay (s)", 0.0, 10.0,
                        valinit=args.window, valstep=0.1)

    heartbeat = {"n": 0}

    def update(_frame):
        now = time.monotonic()
        window = max(win_slider.val, 0.05)   # tiny floor avoids div-by-zero at 0
        with LOCK:
            pts = list(POINTS)
        xs, ys, rgba = [], [], []
        live_n = 0
        for (t, x, y, slot) in pts:
            age = now - t
            if age > window:
                continue
            alpha = max(0.0, 1.0 - age / window)
            if age < 0.2:
                live_n += 1
            r, g, b = SLOT_RGB.get(slot, (1.0, 1.0, 1.0))
            xs.append(x)
            ys.append(y)
            rgba.append((r, g, b, alpha))
        if xs:
            scat.set_offsets(np.column_stack([xs, ys]))
            scat.set_facecolors(rgba)
        else:
            scat.set_offsets(np.empty((0, 2)))
            scat.set_facecolors(np.empty((0, 4)))
        info.set_text(f"window={window:4.1f}s   points={len(xs)}   live={live_n}")
        heartbeat["n"] += 1
        if heartbeat["n"] % 40 == 0:   # ~ every 2 s, so we can confirm it's alive
            print(f"[plot] frames_drawn={heartbeat['n']} stream_lines={STATS['lines']} "
                  f"shown={len(xs)} buffered={len(pts)}", flush=True)
        return scat, info

    # FuncAnimation drives redraws through the backend's own event loop (reliable on
    # macosx). Keep a hard reference on the figure or it gets garbage-collected and stops.
    ani = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    fig._radar_ani = ani

    def on_close(_evt):
        STOP.set()
        proc.terminate()
    fig.canvas.mpl_connect("close_event", on_close)

    try:
        plt.show()
    finally:
        STOP.set()
        proc.terminate()


if __name__ == "__main__":
    main()
