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


def test_stick_defaults_are_enabled() -> None:
    config = Config()
    assert config.stick_body_enabled is True
    assert config.stick_random_action_enabled is True
    assert config.stick_spin_axis == "flip"
    assert config.version == 4


def test_stick_values_are_clamped_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "stick_body_ratio": 9,
                "stick_line_width": 0,
                "stick_action_interval": 3,
                "stick_spin_axis": "nope",
                "stick_color_lei": "red",
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.stick_body_ratio == 1.4
    assert config.stick_line_width == 2.0
    assert config.stick_action_interval == 8
    assert config.stick_spin_axis == "flip"
    assert config.stick_color_lei == "#20242b"


def test_zero_interval_disables_random_actions(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"stick_action_interval": 0}), encoding="utf-8")
    assert load_config(path).stick_action_interval == 0


def test_auto_dialog_and_duel_defaults() -> None:
    """出厂默认：氦气音色、自动溜达、移动后 75% 概率开聊。"""
    config = Config()
    assert config.helium is True
    assert config.wander_enabled is True
    assert config.wander_interval_seconds == 30
    assert config.stick_action_interval == 8
    assert config.crosstalk_lines == 20
    assert config.auto_move_dialog_chance == 75
    assert config.auto_move_dialog_mode == "crosstalk"
    assert config.duel_effect_enabled is True


def test_auto_dialog_values_are_validated(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"auto_move_dialog_chance": 250, "auto_move_dialog_mode": "nope"}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.auto_move_dialog_chance == 100
    assert config.auto_move_dialog_mode == "crosstalk"


def test_frosted_ui_defaults_on(tmp_path: Path) -> None:
    """磨砂只作用于菜单/设置，主窗口保持透明，所以默认开启是安全的。"""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    assert load_config(path).frosted_ui_enabled is True


def test_old_glass_keys_are_ignored(tmp_path: Path) -> None:
    """2.1.x 的 glass_enabled / corner_radius 已废弃，读旧配置不能报错。"""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"glass_enabled": False, "corner_radius": 20}), encoding="utf-8"
    )
    cfg = load_config(path)
    assert cfg.frosted_ui_enabled is True
    assert not hasattr(cfg, "glass_enabled")
