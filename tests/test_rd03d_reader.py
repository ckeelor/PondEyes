# tests.test_rd03d_reader
# =======================
#
# The RD-03D wiring tests: prove the factory maps input_mode "rd03d" to the right reader and
# that the reader is armed to send the multi-target-mode command on open. These verify CONFIG
# and construction only — NO serial port is opened, so they run anywhere (CI, no hardware).

from radar import reader_base
from radar.reader_base import make_reader
from radar.sensors import Sensor
from radar.serial_reader import RadarRD03D, RD03D_MULTI_CMD, RadarSerial


def _noop(_frame, _t):
    pass


def test_factory_maps_rd03d_to_rd03d_reader():
    s = Sensor(id="S1", input_mode="rd03d", serial_port="/dev/serial0", serial_baud=256000)
    reader = make_reader(s, _noop)
    try:
        assert isinstance(reader, RadarRD03D)
        assert reader.port == "/dev/serial0"
        assert reader.baud == 256000
        # Armed to select multi-target mode on open (this is the whole point of the type).
        assert reader.init_cmds == RD03D_MULTI_CMD
    finally:
        reader_base.stop_all_readers()       # don't leak the (never-started) reader registry


def test_plain_serial_reader_sends_nothing_on_open():
    # The LD2450 path stays read-only: no init command, so existing behavior is unchanged.
    s = Sensor(id="S1", input_mode="serial", serial_port="/dev/ttyUSB0", serial_baud=256000)
    reader = make_reader(s, _noop)
    try:
        assert isinstance(reader, RadarSerial) and not isinstance(reader, RadarRD03D)
        assert reader.init_cmds == b""
    finally:
        reader_base.stop_all_readers()


def test_multi_target_command_bytes():
    # Standard Ai-Thinker command frame: header FD FC FB FA, length 02 00, word 90 00
    # (multi-target), footer 04 03 02 01. Guard against an accidental edit to the constant.
    assert RD03D_MULTI_CMD == bytes.fromhex("fdfcfbfa0200900004030201")
