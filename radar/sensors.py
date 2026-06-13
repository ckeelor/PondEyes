# radar.sensors
# =============
#
# The Sensor: one of these per physical radar in the world.
#
# A Sensor bundles the three things that make a radar distinct on the shared map:
#   - IDENTITY   : id, label, color  (color drives marker + FOV cone + that sensor's targets)
#   - TRANSPORT  : how its frames arrive (serial / mqtt / sim, plus the connection params)
#   - POSE       : where it sits on the map (position) and which way it faces (heading)
#
# The key behaviour is local_to_world(): the radar reports targets in ITS OWN frame (x to the
# right, y straight ahead, origin at the sensor). To draw a target on the shared map we must
# rotate by the sensor's heading and translate by its position. Putting that math on the
# Sensor (instead of the GUI) is what lets N sensors each project their own targets correctly.

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from radar import geometry

# A fixed palette to hand out to new sensors so they look distinct by default. The config UI
# color picker can override any of these. Wraps around if there are more sensors than colors.
DEFAULT_PALETTE = [
    "#00ff80", "#ff8800", "#00bfff", "#ff00aa",
    "#ffff00", "#00ffff", "#ff5555", "#aa55ff",
]


@dataclass
class Sensor:
    # ── Identity ────────────────────────────────────────────────────────────────────────
    id: str                          # short unique key, e.g. "S1" or "front_bumper"
    label: str = ""                  # human-friendly name shown in the UI; defaults to id
    color: str = "#00ff80"           # "#rrggbb" base color for marker/FOV/targets
    enabled: bool = True             # if False, no reader is spawned but the sensor stays in cfg/UI
    trail_on: bool = True            # draw this sensor's target trails (per-sensor; master button on main window)

    # ── Transport ───────────────────────────────────────────────────────────────────────
    input_mode: str = "serial"       # "serial" (LD2450) | "rd03d" (Ai-Thinker RD-03D) | "mqtt" | "sim"
    serial_port: str = "/dev/ttyUSB0"
    serial_baud: int = 256000
    broker: str = "127.0.0.1"
    port: int = 1883
    topic: str = "PondEyes/raw"
    sim_pattern: str = "circle"      # trajectory name when input_mode == "sim"
    sim_hz: float = 10.0             # frames/sec the sim emits

    # ── Pose (on the shared world map, in millimetres / degrees) ─────────────────────────
    position: Tuple[float, float] = (0.0, 0.0)
    heading: float = 0.0             # degrees, -180..180; 0 = facing +y (map "up")
    min_range_mm: float = 0.0        # near-side display gate; 0 = none. Targets CLOSER than
                                     # this are hidden + don't beep (excludes undesirable
                                     # near-sensor area). Backend still tracks/logs them.
    max_range_mm: float = 8000.0     # far-side display gate; 0 = unlimited. Default 8 m so a NEW
                                     # sensor shows its shaded active area out of the box. Targets
                                     # beyond this are hidden + don't beep (still tracked/logged).

    # ── Tracking ─────────────────────────────────────────────────────────────────────────
    speed_sensitivity: float = 0.25  # 0 = off; 1 = strictest. Higher = split a track sooner
                                     # when a target "teleports" (the radar reused the slot for
                                     # a different person). Lower for fast runners outdoors.

    def __post_init__(self):
        # A blank label is a nuisance in the UI; fall back to the id.
        if not self.label:
            self.label = self.id

    def local_to_world(self, xl: float, yl: float) -> Tuple[float, float]:
        # Project a sensor-local point (+x right, +y ahead, mm) into WORLD (map) mm using this
        # sensor's pose. The rotation math lives in radar.geometry so the live view, playback, and
        # this method all share one implementation (see geometry.local_to_world).
        return geometry.local_to_world(xl, yl, (self.position[0], self.position[1], self.heading))

    # ── (De)serialisation to/from the plain dicts stored in radar_config.json ────────────
    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "color": self.color,
            "enabled": self.enabled, "trail_on": self.trail_on,
            "input_mode": self.input_mode,
            "serial_port": self.serial_port, "serial_baud": self.serial_baud,
            "broker": self.broker, "port": self.port, "topic": self.topic,
            "sim_pattern": self.sim_pattern, "sim_hz": self.sim_hz,
            "position": list(self.position), "heading": self.heading,
            "min_range_mm": self.min_range_mm, "max_range_mm": self.max_range_mm,
            "speed_sensitivity": self.speed_sensitivity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sensor":
        # Tolerant loader: every field has a default so a partial/legacy dict still yields a
        # usable Sensor. position arrives as a JSON list; we normalise it to a tuple.
        return cls(
            id=d["id"],
            label=d.get("label", ""),
            color=d.get("color", "#00ff80"),
            enabled=bool(d.get("enabled", True)),
            trail_on=bool(d.get("trail_on", True)),
            input_mode=d.get("input_mode", "serial"),
            serial_port=d.get("serial_port", "/dev/ttyUSB0"),
            serial_baud=int(d.get("serial_baud", 256000)),
            broker=d.get("broker", "127.0.0.1"),
            port=int(d.get("port", 1883)),
            topic=d.get("topic", "PondEyes/raw"),
            sim_pattern=d.get("sim_pattern", "circle"),
            sim_hz=float(d.get("sim_hz", 10.0)),
            position=tuple(d.get("position", [0.0, 0.0])),
            heading=float(d.get("heading", 0.0)),
            min_range_mm=float(d.get("min_range_mm", 0.0)),
            max_range_mm=float(d.get("max_range_mm", 8000.0)),
            speed_sensitivity=float(d.get("speed_sensitivity", 0.25)),
        )
