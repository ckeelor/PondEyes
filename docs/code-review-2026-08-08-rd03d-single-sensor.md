# Code Review — `rd03d-single-sensor` branch

**Date:** 2026-08-08
**Reviewer:** Claude Code (senior-tech-lead review, high effort, fixes applied)
**Scope:** Branch diff vs `main` — RD-03D single-sensor support (`radar_monitor.py`, `radar/serial_reader.py`, `radar/frames.py`, `radar_plot.py`)

All five findings below were **fixed in the working tree** as part of this review.

---

## Findings & fixes

### 1. Crash after a failed stall-reopen — `radar_monitor.py` (correctness)

**Problem:** When the PL011 stall-recovery path tried to reopen `/dev/serial0` and the
open itself failed (e.g. the port was momentarily busy), the loop fell through and
called `ser.read(512)` on the closed handle. The monitor died with an uncaught
`PortNotOpenError` traceback instead of recovering.

**Fix:** Reopen failure now retries in a loop — honoring `--seconds` and Ctrl-C — and
also catches `OSError` alongside `SerialException`.

### 2. Unbounded buffer growth on garbage input — `radar_monitor.py` (correctness)

**Problem:** The frame-scan loop never trimmed the buffer when no `AA FF 03 00` header
was present. With a wrong baud or line noise, `buf` grew ~25 KB/s at 256000 baud and
`buf.find()` rescanned the whole thing every pass — memory and CPU climbed steadily on
a long-running Pi Zero session. (`RadarSerial` already kept only a 3-byte tail in the
identical case.)

**Fix:** Headerless garbage is trimmed to a 3-byte tail (mirroring `RadarSerial`), and
pre-header garbage is dropped before rescanning — bounding both memory and CPU.

### 3. No RX-stall recovery in the live GUI reader — `radar/serial_reader.py` (correctness, most important)

**Problem:** `RadarRD03D` lacked the PL011 RX-stall recovery that `radar_monitor.py`
needed on the *same* hardware. If the `cts_event` PL011 quirk wedged the RX side while
the radar kept transmitting, the PondEyes reader thread read nothing forever. A radar
power blip also reverted the sensor to default (single-target) reporting mode with no
re-send of `RD03D_MULTI_CMD` — only one target ever reported until the user manually
reopened inputs.

**Fix:** `_loop` was split into an outer reopen loop plus `_session()`. Readers that
send an init command (RD-03D only) now detect a **3 s RX stall**, reopen the port, and
re-send the mode command. The plain LD2450 path is behavior-identical: it never stalls
out and still exits quietly on `SerialException`.

### 4. Duplicated wire-format constants and decode — `radar_monitor.py` (simplification)

**Problem:** `radar_monitor.py` carried its own copy of the RD-03D multi-target command
bytes and hand-rolled per-slot frame offsets / s15 decode — exactly the drift that
`radar/frames.py`'s own header warns about ("two copies of the binary protocol is a bug
waiting to happen").

**Fix:** `RD03D_MULTI_CMD` / `RD03D_SINGLE_CMD` moved into `radar/frames.py` (the
module's charter is "single home for the wire format"); `serial_reader.py` re-exports
them so `tests/test_rd03d_reader.py` imports still work. Added `parse_full()` returning
`(slot, x, y, speed)`, with `parse()` now derived from it. `radar_monitor.py` uses both
instead of its private copies — and stays pygame-free since it imports only
`radar.frames`.

### 5. Docstring drift — `radar_plot.py` (docs)

**Problem:** Module docstring said the decay slider spans 0..10 s; the Slider (and
`--window` help) actually allow 0..30 s.

**Fix:** Docstring corrected to 0..30 s.

---

## Verification

- `tests/test_frames.py` passes **8/8**, including a new `test_parse_full_keeps_speed`.
- pygame/pyserial are not installed on the Mac dev machine (pre-existing), so the
  GUI/reader suites can't run there. Stub-based checks covered: reader factory wiring,
  init-command send, frame delivery, stall-vs-stop session outcomes, and the monitor's
  full parse loop (garbage trim, split-frame reassembly, bad-footer drop) — all passed.

## Follow-ups before merging

- [ ] **Soak-test on the Pi Zero 2 W** — the stall-recovery change in
      `serial_reader.py` is the one fix only real hardware can prove out. Run the GUI
      for a while and power-cycle the sensor to confirm it re-enters multi-target mode
      on its own.
- [ ] Commit the review fixes (they were left uncommitted in the working tree at
      review time).
