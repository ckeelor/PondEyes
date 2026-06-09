# tests.test_fake_reader
# ======================
#
# Unit tests for radar/reader_base.py — the Reader abstraction and FakeReader.
#
# FakeReader is the linchpin of hardware-free testing, so we verify the two things the rest
# of the suite depends on:
#   1. In manual-clock mode it emits EXACTLY one frame per tick(), in the same (slot,x,y,hex)
#      shape a real reader produces.
#   2. make_reader() returns the right Reader subclass for each input_mode.

from radar import trajectories
from radar.reader_base import Reader, FakeReader, make_reader
from radar.serial_reader import RadarSerial
from radar.mqtt_client import RadarMQTT
from radar.sensors import Sensor


def test_real_readers_are_reader_subclasses():
    assert issubclass(RadarSerial, Reader)
    assert issubclass(RadarMQTT, Reader)


def test_fake_reader_manual_clock_emits_one_frame_per_tick():
    got = []
    fr = FakeReader(lambda lst, t: got.append(lst),     # callback is (frame, t_mono) now
                    trajectories.static(x=132, y=196), manual=True)
    fr.start()                              # no-op in manual mode (no thread)
    fr.tick(0.0)
    fr.tick(0.1)
    assert len(got) == 2                    # exactly one delivery per tick
    # Each delivery is a list of (slot, x, y, raw_hex) tuples matching a real reader.
    slot, x, y, raw_hex = got[0][0]
    assert (slot, x, y) == (1, 132, 196)
    assert isinstance(raw_hex, str) and len(raw_hex) == 60   # 30 bytes -> 60 hex chars


def test_fake_reader_frames_match_trajectory():
    # Circle r=1000, period=4, centre (0,2000): t=0 -> (1000,2000); t=1 -> (~0,3000).
    got = []
    fr = FakeReader(lambda lst, t: got.append(lst),
                    trajectories.circle(r=1000, period=4.0, cx=0, cy=2000), manual=True)
    fr.tick(0.0)
    fr.tick(1.0)
    assert (got[0][0][1], got[0][0][2]) == (1000, 2000)
    assert got[1][0][2] == 3000


def test_make_reader_dispatch():
    cb = lambda lst, t: None
    assert isinstance(make_reader(Sensor(id="A", input_mode="sim"), cb), FakeReader)
    assert isinstance(make_reader(Sensor(id="B", input_mode="serial"), cb), RadarSerial)
    assert isinstance(make_reader(Sensor(id="C", input_mode="mqtt"), cb), RadarMQTT)
    # Stop the MQTT reader's worker thread so it doesn't linger after the test.
    make_reader(Sensor(id="D", input_mode="mqtt"), cb).stop()


def test_stop_all_readers_backstop():
    # macOS broadcasts serial input to EVERY open handle, so even one leaked reader thread
    # double-counts frames (the "36 Hz from a 12 fps module" bug). make_reader registers every
    # reader; stop_all_readers must terminate ALL of them so re-opening starts from a clean slate.
    import time
    from radar import reader_base
    from radar.reader_base import stop_all_readers
    reader_base._ACTIVE_READERS.clear()
    rs = [make_reader(Sensor(id=f"S{i}", input_mode="sim", sim_pattern="static", sim_hz=30.0),
                      lambda lst, t: None) for i in range(3)]
    for r in rs:
        r.start()
    time.sleep(0.05)
    assert all(r._thread and r._thread.is_alive() for r in rs)   # 3 live "leaked" readers
    assert len(reader_base._ACTIVE_READERS) == 3
    stop_all_readers()
    time.sleep(0.1)
    assert not any(r._thread and r._thread.is_alive() for r in rs)
    assert reader_base._ACTIVE_READERS == []
