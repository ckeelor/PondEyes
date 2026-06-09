# tools/csv_to_sqlite.py
# ======================
#
# One-time importer: pull legacy per-track CSV logs (the pre-v4 format under
# log/YYYY-MM-DD_targets_tracked/) into the new SQLite track store, so old recordings remain
# visible to the SQLite-based playback viewer.
#
# Legacy logs predate multi-sensor, so every imported track is attributed to a default sensor
# ("S1") with a zero pose. The import is IDEMPOTENT: a track already present (matched by serial
# + first_seen) is skipped, so re-running is safe.
#
# Usage:
#   .venv/bin/python tools/csv_to_sqlite.py [--db pondeyes.db] [--log-dir log/] [--sensor S1]

from __future__ import annotations

import argparse
import csv
from pathlib import Path

# Make `radar` importable when this script is run from the project root.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar.store import TrackStore           # noqa: E402
from radar.constants import LOG_DIR, ROOT    # noqa: E402

# A minimal default sensor row so the tracks foreign key resolves for imported data.
DEFAULT_SENSOR = {
    "id": "S1", "label": "Sensor 1 (imported)", "color": "#00ff80", "enabled": True,
    "input_mode": "serial", "serial_port": "", "serial_baud": 256000,
    "broker": "", "port": 1883, "topic": "", "position": [0, 0], "heading": 0.0,
}


def _already_imported(store: TrackStore, serial: str, first_seen: str) -> bool:
    row = store.conn.execute(
        "SELECT id FROM tracks WHERE serial=? AND first_seen=?", (serial, first_seen)
    ).fetchone()
    return row is not None


def import_day(store: TrackStore, day_dir: Path, sensor_id: str) -> int:
    # Import one YYYY-MM-DD_targets_tracked/ directory using its sibling TrackIndex CSV as the
    # list of tracks. Returns the number of tracks imported.
    stem = day_dir.name.replace("_targets_tracked", "")
    index = day_dir.parent / f"{stem}_TrackIndex.csv"
    if not index.exists():
        return 0

    imported = 0
    with index.open() as fh:
        for row in csv.DictReader(fh):
            serial = row.get("serial", "")
            first_seen = row.get("first_seen_iso", "")
            verbose = day_dir / row.get("verbose_file", "")
            if not serial or not verbose.exists():
                continue
            if _already_imported(store, serial, first_seen):
                continue

            track_id = store.open_track(sensor_id, serial, (0.0, 0.0, 0.0), first_seen)
            with verbose.open() as vfh:
                rdr = csv.reader(vfh)
                next(rdr, None)                       # skip header
                for r in rdr:
                    # legacy columns: t_iso, x, y, range, speed, accel, raw_hex
                    if len(r) < 3:
                        continue
                    store.append_point(
                        track_id, r[0], int(r[1]), int(r[2]),
                        int(r[3]) if len(r) > 3 and r[3] else 0,
                        float(r[4]) if len(r) > 4 and r[4] else 0.0,
                        float(r[5]) if len(r) > 5 and r[5] else 0.0,
                        r[6] if len(r) > 6 else "",
                    )
            store.close_track(track_id, row.get("last_seen_iso", first_seen), 0.0)
            imported += 1
    return imported


def main():
    ap = argparse.ArgumentParser(description="Import legacy CSV logs into the SQLite store.")
    ap.add_argument("--db", default=str(ROOT / "pondeyes.db"))
    ap.add_argument("--log-dir", default=str(LOG_DIR))
    ap.add_argument("--sensor", default="S1", help="sensor id to attribute imported tracks to")
    args = ap.parse_args()

    store = TrackStore(Path(args.db))
    store.upsert_sensor({**DEFAULT_SENSOR, "id": args.sensor})

    total = 0
    for day in sorted(Path(args.log_dir).glob("*_targets_tracked")):
        n = import_day(store, day, args.sensor)
        print(f"{day.name}: imported {n} track(s)")
        total += n
    store.close()
    print(f"Done. {total} track(s) imported into {args.db}")


if __name__ == "__main__":
    main()
