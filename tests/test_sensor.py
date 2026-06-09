# tests.test_sensor
# =================
#
# Unit tests for radar/sensors.py — focused on local_to_world(), the projection that turns a
# radar's own (x-right, y-ahead) readings into world-map coordinates. Getting the rotation
# sign right is the whole game for multi-sensor: a sign slip would mirror a sensor's targets.

import math

import pytest

from radar.sensors import Sensor


def test_heading_zero_is_pure_translation():
    # At heading 0 the local frame and world frame are aligned, so projecting is just adding
    # the sensor position. Local "straight ahead" (0, 1000) lands 1000mm above the sensor.
    s = Sensor(id="S1", position=(500, 700), heading=0.0)
    assert s.local_to_world(0, 1000) == pytest.approx((500, 1700))
    assert s.local_to_world(300, 0) == pytest.approx((800, 700))


def test_rotation_90_degrees():
    # Heading 90: cos=0, sin=1  ->  world_x = pos_x + yl ; world_y = pos_y - xl.
    s = Sensor(id="S1", position=(0, 0), heading=90.0)
    assert s.local_to_world(0, 1000) == pytest.approx((1000, 0))     # ahead -> +x
    assert s.local_to_world(1000, 0) == pytest.approx((0, -1000))    # right -> -y


def test_rotation_180_degrees():
    # Heading 180 flips both axes: straight-ahead points to -y, right points to -x.
    s = Sensor(id="S1", position=(0, 0), heading=180.0)
    assert s.local_to_world(0, 1000) == pytest.approx((0, -1000))
    assert s.local_to_world(1000, 0) == pytest.approx((-1000, 0))


def test_rotation_270_degrees():
    # Heading 270 (== -90): ahead -> -x, right -> +y.
    s = Sensor(id="S1", position=(0, 0), heading=270.0)
    assert s.local_to_world(0, 1000) == pytest.approx((-1000, 0))
    assert s.local_to_world(1000, 0) == pytest.approx((0, 1000))


def test_to_from_dict_round_trip():
    # A Sensor serialised to a dict and back must be unchanged — this is what config save/load
    # relies on. position comes back as a tuple even though JSON stores it as a list.
    s = Sensor(id="S2", label="Rear", color="#ff8800", input_mode="mqtt",
               topic="PondEyes/raw_rear", position=(1234.5, 6789.0), heading=42.0)
    s2 = Sensor.from_dict(s.to_dict())
    assert s2 == s


def test_blank_label_defaults_to_id():
    assert Sensor(id="frontdoor").label == "frontdoor"


def test_max_range_round_trip():
    s = Sensor(id="S1", max_range_mm=1500.0)
    assert Sensor.from_dict(s.to_dict()).max_range_mm == 1500.0
    assert Sensor(id="S2").max_range_mm == 8000.0       # default 8 m (shaded area shows by default)
    assert Sensor(id="S3").min_range_mm == 0.0          # near gate off by default


def test_speed_sensitivity_round_trip():
    s = Sensor(id="S1", speed_sensitivity=0.7)
    assert Sensor.from_dict(s.to_dict()).speed_sensitivity == 0.7
    assert Sensor(id="S2").speed_sensitivity == 0.25    # default
