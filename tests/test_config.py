"""config 模块测试。"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from leiyu_pet.config import DEFAULTS, Config, load_config, save_config


def test_defaults_match_dataclass() -> None:
    cfg = Config()
    for key, default in DEFAULTS.items():
        assert getattr(cfg, key) == default


def test_defaults_keys_equal_field_names() -> None:
    assert set(DEFAULTS) == {f.name for f in fields(Config)}


def test_load_missing_keys_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"volume": 0.3}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.volume == 0.3
    assert cfg.distance == DEFAULTS["distance"]
    assert cfg.helium == DEFAULTS["helium"]


def test_load_clamps_volume(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"volume": 5}), encoding="utf-8")
    assert load_config(path).volume == 1.0
    path.write_text(json.dumps({"volume": -1}), encoding="utf-8")
    assert load_config(path).volume == 0.0


def test_load_clamps_distance(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"distance": 200}), encoding="utf-8")
    assert load_config(path).distance == 100
    path.write_text(json.dumps({"distance": -5}), encoding="utf-8")
    assert load_config(path).distance == 0


def test_load_coerces_bool(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"helium": "yes", "autostart": 0}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.helium is True
    assert cfg.autostart is False


def test_load_normalizes_version(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 0}), encoding="utf-8")
    assert load_config(path).version == 1
    path.write_text(json.dumps({"version": 4}), encoding="utf-8")
    assert load_config(path).version == 4


def test_load_ignores_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 2, "unknown": 99}), encoding="utf-8")
    cfg = load_config(path)
    assert not hasattr(cfg, "unknown")
    assert cfg.version == 2


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.json")
    assert cfg == Config(**DEFAULTS)


def test_load_bad_json_backs_up_and_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    cfg = load_config(path)
    assert cfg == Config(**DEFAULTS)
    assert path.with_suffix(".json.bak").is_file()


def test_save_is_atomic_and_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = Config(volume=0.5, distance=10, autostart=True)
    save_config(cfg, path)
    assert not path.with_suffix(".tmp").exists()
    loaded = load_config(path)
    assert loaded.volume == 0.5
    assert loaded.distance == 10
    assert loaded.autostart is True


def test_save_only_writes_whitelisted_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config(Config(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == set(DEFAULTS)


def test_new_settings_are_clamped_and_normalized(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "caption_font_size": 99,
                "opacity": 5,
                "break_reminder_minutes": -1,
                "pomodoro_focus_minutes": 999,
                "pomodoro_break_minutes": 0,
                "wander_interval_seconds": 1,
                "quiet_start": "7:5",
                "quiet_end": "bad",
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.caption_font_size == 20
    assert cfg.opacity == 1.0
    assert cfg.break_reminder_minutes == 0
    assert cfg.pomodoro_focus_minutes == 120
    assert cfg.pomodoro_break_minutes == 1
    assert cfg.wander_interval_seconds == 10
    assert cfg.quiet_start == "07:05"
    assert cfg.quiet_end == "08:00"


def test_opacity_lower_bound(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"opacity": 0.0}), encoding="utf-8")
    assert load_config(path).opacity == 0.3
