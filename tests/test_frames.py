# tests.test_frames
# =================
#
# Unit tests for radar/frames.py — the LD2450 wire-format codec.
#
# The single most important test here is the build -> parse ROUND-TRIP: because the encoder
# (build_frame) and decoder (parse/s15) are exact inverses of an unusual sign-flag format,
# any drift between them would silently corrupt every synthetic frame our tests and the
# simulator produce. Round-tripping pins the two halves together forever.

from radar import frames


# ── s15 decode: the sign-flag convention (MSB set = positive) ───────────────────────────
def test_s15_sign_flag_convention():
    # MSB (0x8000) set -> positive; clear -> negative; magnitude in the low 15 bits.
    assert frames.s15(0x8084) == 132     # real value seen on hardware (x of a live target)
    assert frames.s15(0x030E) == -782
    assert frames.s15(0x8000) == 0       # +0 (sign flag set, zero magnitude)
    assert frames.s15(0x0000) == 0       # -0 collapses to 0 as well


# ── build -> parse round-trip, including a negative coordinate ──────────────────────────
def test_build_parse_round_trip():
    f = frames.build_frame([(132, 196, 0), (-782, -363, -8)])
    assert frames.is_complete_frame(f)
    # parse() reports (slot, x, y) for non-empty slots, 1-based slot numbers.
    assert frames.parse(f) == [(1, 132, 196), (2, -782, -363)]


# ── a real frame captured off the LD2450 (via the ESP32 bridge) decodes correctly ───────
def test_decode_real_captured_frame():
    real = bytes.fromhex(
        "aaff0300"            # header
        "8480c4800000 6801".replace(" ", "")   # target 1: x=132, y=196, v=0, gate
        + "00" * 16           # targets 2 and 3 empty
        + "55cc"              # footer
    )
    assert len(real) == frames.FLEN
    assert frames.parse(real) == [(1, 132, 196)]


# ── empty slots are filtered; an all-empty frame yields no targets ──────────────────────
def test_empty_slots_filtered():
    assert frames.parse(frames.build_frame([])) == []
    # one target in slot 1, slots 2 & 3 empty -> single-element list
    assert frames.parse(frames.build_frame([(10, 20, 0)])) == [(1, 10, 20)]


# ── validation: wrong length / header / footer are rejected ─────────────────────────────
def test_is_complete_frame_rejects_malformed():
    good = frames.build_frame([(1, 1, 0)])
    assert frames.is_complete_frame(good)
    assert not frames.is_complete_frame(good[:-1])            # too short
    assert not frames.is_complete_frame(b"\x00" * frames.FLEN)  # bad header/footer
    assert not frames.is_complete_frame(good[:28] + b"\x00\x00")  # bad footer


# ── build_frame refuses more than three targets (hardware limit) ────────────────────────
def test_build_frame_rejects_too_many_targets():
    import pytest
    with pytest.raises(ValueError):
        frames.build_frame([(0, 0, 0)] * 4)
