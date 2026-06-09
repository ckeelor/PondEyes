# radar.frames
# ============
#
# The single home for the HLK-LD2450 wire format.
#
# Before this module, the exact same byte-level knowledge (header/footer constants, the
# signed-15-bit decode, the per-target offsets) lived TWICE — copy-pasted into both
# radar/serial_reader.py and radar/mqtt_client.py. Two copies of a binary protocol is a bug
# waiting to happen: fix a sign convention in one place, forget the other, and only one
# transport breaks. Centralising it here means the wire format is defined exactly once and
# every reader (real serial, real MQTT, or the in-process FakeReader used by tests) agrees.
#
# ----------------------------------------------------------------------------------------
# The LD2450 frame, byte by byte (30 bytes total)
# ----------------------------------------------------------------------------------------
#   offset  bytes  meaning
#   ------  -----  -------------------------------------------------------------
#     0      4     HEADER  = AA FF 03 00   (fixed; marks the start of a frame)
#     4      8     target 1  -> x(2) y(2) speed(2) distance_gate(2)
#    12      8     target 2  -> x(2) y(2) speed(2) distance_gate(2)
#    20      8     target 3  -> x(2) y(2) speed(2) distance_gate(2)
#    28      2     FOOTER  = 55 CC         (fixed; marks the end of a frame)
#
# Every multi-byte field is LITTLE-ENDIAN. The module reports up to 3 simultaneous targets
# per frame; an unused slot is all-zero bytes. x/y are millimetres relative to the sensor;
# speed is mm/s; the distance gate is an internal range bucket we don't use.
#
# ----------------------------------------------------------------------------------------
# The signed-15-bit quirk (the part that trips everyone up)
# ----------------------------------------------------------------------------------------
# The LD2450 does NOT use ordinary two's-complement for x/y/speed. Instead the top bit
# (0x8000) is a SIGN FLAG and the low 15 bits (0x7FFF) are the MAGNITUDE:
#
#     MSB = 1  ->  value is POSITIVE,  magnitude = word & 0x7FFF
#     MSB = 0  ->  value is NEGATIVE,  magnitude = word & 0x7FFF
#
# So 0x8084 decodes to +132, and 0x030E decodes to -782. This is unusual enough that the
# encoder (build_frame) and decoder (s15) must be exact inverses — tests/test_frames.py
# asserts a build->parse round-trip precisely to guard this.

from __future__ import annotations

from typing import List, Sequence, Tuple

# ── Fixed framing constants ─────────────────────────────────────────────────────────────
# Kept as module-level `bytes` so callers can do `buf.startswith(HDR)` etc. directly.
HDR = bytes.fromhex("AAFF0300")   # 4-byte start-of-frame marker
FTR = bytes.fromhex("55CC")       # 2-byte end-of-frame marker
FLEN = 30                         # a complete frame is always exactly 30 bytes


def s15(word: int) -> int:
    # Decode one LD2450 signed-15-bit `word` (0..65535) into a Python int.
    # Rule (see header): the 0x8000 bit is the sign FLAG (set = positive), and the low 15
    # bits are the magnitude.   s15(0x8084) -> 132 ;  s15(0x030E) -> -782
    magnitude = word & 0x7FFF
    return magnitude if (word & 0x8000) else -magnitude


def _encode_s15(value: int) -> int:
    # Inverse of s15: encode a signed Python int back into a 16-bit LD2450 word.
    # Mirror of the decode rule — set the sign flag for non-negative values, store
    # abs(value) in the low 15 bits. We clamp the magnitude to 15 bits so a pathological
    # input can never corrupt the sign flag.   _encode_s15(132) -> 0x8084 ; (-782) -> 0x030E
    #
    # NOTE: the tempting one-liner `(value & 0x7FFF) | (0x8000 if value >= 0 else 0)` is
    # WRONG for negatives, because Python's `&` on a negative int yields two's-complement
    # low bits (e.g. -782 & 0x7FFF == 0x7CF2), not the magnitude. We must use abs().
    magnitude = abs(int(value)) & 0x7FFF
    sign_flag = 0x8000 if value >= 0 else 0x0000
    return magnitude | sign_flag


def is_complete_frame(buf: bytes) -> bool:
    # True iff `buf` is a single, well-formed 30-byte frame (right length, header, footer).
    # Readers call this to validate a candidate buffer before trusting it.
    return (
        len(buf) >= FLEN
        and buf[:4] == HDR
        and buf[FLEN - 2 : FLEN] == FTR
    )


def parse(buf: bytes) -> List[Tuple[int, int, int]]:
    # Parse one LD2450 frame into a list of active targets.
    #
    # Returns a list of (slot, x_mm, y_mm) tuples, where `slot` is 1-based (1, 2, or 3) to
    # match the convention the rest of the app already uses. Empty slots — where both x and
    # y decode to 0 — are filtered out, so a frame with one person yields a 1-element list.
    #
    # We intentionally decode only x and y here (not the frame's speed field): the app
    # derives velocity/acceleration from successive positions in radar/tracking.py, and
    # keeping parse's output shape identical to the historical readers means Phase 0 changes
    # nothing observable. The caller is responsible for header/footer validation (see
    # is_complete_frame); this function trusts that `buf` is at least FLEN bytes.
    targets: List[Tuple[int, int, int]] = []
    for i in range(3):                       # up to three targets per frame
        off = 4 + i * 8                      # skip the 4-byte header, 8 bytes per target
        x = s15(int.from_bytes(buf[off : off + 2], "little"))
        y = s15(int.from_bytes(buf[off + 2 : off + 4], "little"))
        if x or y:                           # (0, 0) means "this slot is empty" -> skip
            targets.append((i + 1, x, y))
    return targets


def build_frame(
    targets: Sequence[Tuple[int, int, int]],
    distance_gate: int = 0x0168,
) -> bytes:
    # Encode up to three targets into a 30-byte LD2450 frame — the inverse of parse().
    #
    # `targets` is a sequence of up to 3 (x_mm, y_mm, speed_mm_s) tuples. speed_mm_s is
    # optional per tuple (defaults to 0 if a 2-tuple is given). Fewer than 3 targets pads the
    # remaining slots with the all-zero "empty slot" pattern. `distance_gate` is an internal
    # LD2450 range value we don't interpret; the default mirrors a value seen in real
    # captured frames so synthetic frames look realistic.
    #
    # This single encoder is shared by FakeReader (in-process test/sim source) and
    # tools/sim_sensor.py (MQTT publisher), so emulated frames are byte-for-byte the same
    # shape the hardware produces. tests/test_frames.py round-trips build -> parse to prove
    # the encode/decode pair stays consistent forever.
    #
    #   build_frame([(132, 196, 0)])  ->  parse() == [(1, 132, 196)]
    if len(targets) > 3:
        raise ValueError(f"LD2450 frames hold at most 3 targets, got {len(targets)}")

    out = bytearray(HDR)                      # start with the 4-byte header
    for i in range(3):                        # always emit exactly three 8-byte slots
        if i < len(targets):
            t = targets[i]
            x, y = t[0], t[1]
            speed = t[2] if len(t) > 2 else 0
            out += _encode_s15(x).to_bytes(2, "little")
            out += _encode_s15(y).to_bytes(2, "little")
            out += _encode_s15(speed).to_bytes(2, "little")
            out += (distance_gate & 0xFFFF).to_bytes(2, "little")
        else:
            out += b"\x00" * 8                # empty slot -> all zeros
    out += FTR                                # finish with the 2-byte footer
    assert len(out) == FLEN, "internal error: built frame is not 30 bytes"
    return bytes(out)
