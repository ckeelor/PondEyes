# tests.test_config_migration
# ===========================
#
# The migration is the promise that an existing single-sensor user loses nothing. These tests
# pin the v1 -> v2 fold: flat keys move into sensors[0], calibrated pose is preserved, global
# keys stay put, and a file already at v2 is left alone.

from radar import config


def test_migrate_v1_folds_flat_keys_into_one_sensor():
    v1 = {
        "input_mode": "serial", "serial_port": "/dev/cu.usbserial-X", "serial_baud": 256000,
        "broker": "192.0.2.5", "port": 1883, "topic": "PondEyes/raw",   # 192.0.2.0/24 = RFC5737 doc range
        "sensor": [3140.41, 4687.03], "heading": 42.0,         # v1 pose keys
        "map": "house.svg", "trail_on": True, "smooth_level": 4,  # global keys
    }
    out = config._migrate(dict(v1))

    assert out["schema_version"] == 2
    assert isinstance(out["sensors"], list) and len(out["sensors"]) == 1
    s = out["sensors"][0]
    # calibrated pose preserved exactly
    assert s["position"] == [3140.41, 4687.03]
    assert s["heading"] == 42.0
    # transport folded in
    assert s["input_mode"] == "serial"
    assert s["serial_port"] == "/dev/cu.usbserial-X"
    assert s["topic"] == "PondEyes/raw"
    # old flat keys removed from the top level
    for k in ("sensor", "heading", "input_mode", "serial_port", "broker", "topic"):
        assert k not in out
    # global keys retained at top level
    assert out["map"] == "house.svg" and out["smooth_level"] == 4


def test_migrate_v2_is_passthrough():
    v2 = {"schema_version": 2, "sensors": [{"id": "S1"}], "map": "m.svg"}
    out = config._migrate(dict(v2))
    assert out["sensors"] == [{"id": "S1"}]
    assert out["schema_version"] == 2


def test_load_migrates_file_and_writes_backup(tmp_path, monkeypatch):
    # Point config at a temp file holding a v1 config, then load() and assert it migrates and
    # leaves a .bak of the original.
    import json
    from radar import constants
    cfg_path = tmp_path / "radar_config.json"
    cfg_path.write_text(json.dumps({"input_mode": "serial", "sensor": [1, 2], "heading": 5}))
    monkeypatch.setattr(constants, "CFG_PATH", cfg_path)
    monkeypatch.setattr(config, "CFG_PATH", cfg_path)

    cfg = config.load()
    assert cfg["schema_version"] == 2
    assert cfg["sensors"][0]["position"] == [1, 2]
    assert cfg["sensors"][0]["heading"] == 5
    assert (tmp_path / "radar_config.json.bak").exists()   # original preserved
