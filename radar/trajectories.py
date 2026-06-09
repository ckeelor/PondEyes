# radar.trajectories
# ==================
#
# Pure, reusable target-motion generators for SIMULATED sensors.
#
# Each generator is a factory: you call e.g. circle(r=2000) and get back a function
# `f(t) -> [(x_mm, y_mm, speed_mm_s), ...]` that, given a time in seconds, returns the
# target positions at that instant (up to 3 targets, though these built-ins emit one).
#
# Why factories-returning-functions instead of plain functions? Because a trajectory has
# fixed parameters (radius, period, centre) but a varying input (time). Capturing the
# parameters in a closure gives us a clean single-argument `f(t)` that both FakeReader
# (live sim) and tools/sim_sensor.py (MQTT publisher) can drive identically.
#
# IMPORTANT for tests: these must be DETERMINISTIC. The math-based ones (static/line/circle)
# are naturally pure in `t`. random_walk is seeded, so the same seed + same sequence of `t`
# values always produces the same path — which is what lets manual-clock tests assert exact
# positions.

from __future__ import annotations

import math
import random
from typing import Callable, List, Tuple

# A trajectory is a function of time (seconds) returning a list of (x, y, speed) targets.
Trajectory = Callable[[float], List[Tuple[int, int, int]]]


def static(x: int = 0, y: int = 2000) -> Trajectory:
    # A stationary target sitting at (x, y). Speed is always 0.
    def f(t: float) -> List[Tuple[int, int, int]]:
        return [(int(x), int(y), 0)]
    return f


def line(x0: int = -2000, x1: int = 2000, y: int = 2000, period: float = 8.0) -> Trajectory:
    # A target sweeping back and forth along a horizontal line at fixed depth `y`.
    # We drive x with a sine so the motion eases at the turn-arounds (more lifelike than a
    # sawtooth), and report the analytic derivative as the instantaneous speed.
    def f(t: float) -> List[Tuple[int, int, int]]:
        phase = 2 * math.pi * t / period
        frac = (math.sin(phase) + 1) / 2          # 0..1 ping-pong
        x = x0 + (x1 - x0) * frac
        # d(x)/dt = (x1-x0) * (pi/period) * cos(phase)  -> signed speed in mm/s
        v = (x1 - x0) * (math.pi / period) * math.cos(phase)
        return [(int(x), int(y), int(v))]
    return f


def circle(r: int = 2000, period: float = 8.0, cx: int = 0, cy: int = 2500) -> Trajectory:
    # A target orbiting a circle of radius `r` centred at (cx, cy), one lap per `period`.
    # Tangential speed of uniform circular motion is constant: v = 2*pi*r / period.
    def f(t: float) -> List[Tuple[int, int, int]]:
        ang = 2 * math.pi * t / period
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        v = 2 * math.pi * r / period
        return [(int(x), int(y), int(v))]
    return f


def random_walk(seed: int = 0, step: int = 80, x0: int = 0, y0: int = 2000) -> Trajectory:
    # A jittery target that wanders by a random step each call. Seeded for determinism:
    # same seed + same number of calls => same path. NOTE this generator is stateful (it
    # accumulates position across calls) and ignores the absolute value of `t` — it advances
    # once per invocation. That's fine for both live sim and manual-clock tests, as long as
    # tests call it a fixed number of times.
    rng = random.Random(seed)
    state = {"x": int(x0), "y": int(y0)}

    def f(t: float) -> List[Tuple[int, int, int]]:
        state["x"] += rng.randint(-step, step)
        state["y"] += rng.randint(-step, step)
        # report a rough speed proportional to the step magnitude (cosmetic for coloring)
        return [(state["x"], state["y"], step * 10)]
    return f


# Registry so a config string (sensor.sim_pattern) can be resolved to a trajectory.
_FACTORIES = {
    "static": static,
    "line": line,
    "circle": circle,
    "random_walk": random_walk,
}


def make(name: str, **kwargs) -> Trajectory:
    # Resolve a trajectory by name (used by make_reader for input_mode == "sim").
    # Unknown names fall back to a gentle circle so a typo never crashes a sim run.
    factory = _FACTORIES.get(name.lower(), circle)
    return factory(**kwargs)
