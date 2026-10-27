"""应用配置（Config）的默认值、加载与原子保存。

新增配置键需要同步修改三处：
  1) ``Config`` dataclass 的字段与默认值；
  2) 下面的 ``DEFAULTS`` 字典（它同时作为加载白名单与保存白名单）；
  3) ``tests/test_config.py`` 中对应的默认值快照与键集合断言。

``load_config`` 永不向调用方抛异常：解析失败会把坏文件重命名为 ``.bak`` 并回退默认值。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULTS: dict[str, object] = {
    "version": 4,
    "volume": 0.65,
    "distance": 32,
    "tilt_enabled": True,
    "helium": False,
    "include_explicit": False,
    "autostart": False,
    "click_through": False,
    "lock_position": False,
    "lei_visible": True,
    "yu_visible": True,
    # 相声模式默认句数与是否记住窗口位置
    "crosstalk_lines": 6,
    "remember_position": True,
    "lei_pos": [],
    "yu_pos": [],
    # 系统集成开关
    "hotkeys_enabled": True,
    "check_updates": True,
    "reduce_motion": False,
    "lei_size": 220,
    "yu_size": 220,
    "playback_rate": 1.0,
    # 外观
    "caption_font_size": 11,
    "opacity": 1.0,
    "always_on_top": True,
    # 免打扰时段
    "quiet_hours_enabled": False,
    "quiet_start": "23:00",
    "quiet_end": "08:00",
    # 提醒与番茄钟
    "hourly_chime": False,
    "break_reminder_minutes": 0,
    "pomodoro_focus_minutes": 25,
    "pomodoro_break_minutes": 5,
    # 自动游走与重叠彩蛋
    "wander_enabled": False,
    "wander_interval_seconds": 45,
    "overlap_easter_egg": False,
    # 两只脸部间隙小于该像素值即视为「靠在一起」，触发自动互喷。
    "overlap_trigger_gap": 24.0,
    # 火柴人躯体
    "stick_body_enabled": True,
    "stick_random_action_enabled": True,
    "stick_body_ratio": 0.85,
    "stick_line_width": 5.0,
    "stick_neck_overlap": 6.0,
    "stick_color_lei": "#20242b",
    "stick_color_yu": "#2a2430",
    "stick_action_interval": 12,
    # 自转轴向：flip = Y 轴翻转（默认），roll = 旧版平面滚转
    "stick_spin_axis": "flip",
    # 自动移动后按概率发起对话
    "auto_move_dialog_chance": 0,
    "auto_move_dialog_mode": "crosstalk",
    # 对话开场的决斗特效（纯视觉，与决战模式无关）
    "duel_effect_enabled": True,
    # 分类磨砂：只作用于右键/托盘菜单与设置窗口（主窗口永远绝对透明）
    "frosted_ui_enabled": True,
}


@dataclass(slots=True)
class Config:
    version: int = 4
    volume: float = 0.65
    distance: int = 32
    tilt_enabled: bool = True
    helium: bool = False
    include_explicit: bool = False
    autostart: bool = False
    click_through: bool = False
    lock_position: bool = False
    lei_visible: bool = True
    yu_visible: bool = True
    crosstalk_lines: int = 6
    remember_position: bool = True
    lei_pos: list[int] = field(default_factory=list)
    yu_pos: list[int] = field(default_factory=list)
    hotkeys_enabled: bool = True
    check_updates: bool = True
    reduce_motion: bool = False
    lei_size: int = 220
    yu_size: int = 220
    playback_rate: float = 1.0
    caption_font_size: int = 11
    opacity: float = 1.0
    always_on_top: bool = True
    quiet_hours_enabled: bool = False
    quiet_start: str = "23:00"
    quiet_end: str = "08:00"
    hourly_chime: bool = False
    break_reminder_minutes: int = 0
    pomodoro_focus_minutes: int = 25
    pomodoro_break_minutes: int = 5
    wander_enabled: bool = False
    wander_interval_seconds: int = 45
    overlap_easter_egg: bool = False
    overlap_trigger_gap: float = 24.0
    stick_body_enabled: bool = True
    stick_random_action_enabled: bool = True
    stick_body_ratio: float = 0.85
    stick_line_width: float = 5.0
    stick_neck_overlap: float = 6.0
    stick_color_lei: str = "#20242b"
    stick_color_yu: str = "#2a2430"
    stick_action_interval: int = 12
    stick_spin_axis: str = "flip"
    auto_move_dialog_chance: int = 0
    auto_move_dialog_mode: str = "crosstalk"
    duel_effect_enabled: bool = True
    frosted_ui_enabled: bool = True


def _defaults() -> dict[str, object]:
    """返回一份全新的默认值，避免可变默认值（位置列表）在实例间共享。"""
    return {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in DEFAULTS.items()
    }


def _coerce(key: str, value: object) -> object:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, list):
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return [int(value[0]), int(value[1])]
            except (TypeError, ValueError):
                return []
        return []
    if isinstance(default, int):
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        if key == "version":
            return number if number >= 1 else 1
        if key == "distance":
            return min(max(number, 0), 100)
        if key == "crosstalk_lines":
            return min(max(number, 2), 20)
        if key in {"lei_size", "yu_size"}:
            return min(max(number, 150), 340)
        if key == "caption_font_size":
            return min(max(number, 9), 20)
        if key == "break_reminder_minutes":
            return min(max(number, 0), 240)
        if key == "pomodoro_focus_minutes":
            return min(max(number, 5), 120)
        if key == "pomodoro_break_minutes":
            return min(max(number, 1), 60)
        if key == "wander_interval_seconds":
            return min(max(number, 10), 600)
        if key == "auto_move_dialog_chance":
            return min(max(number, 0), 100)
        if key == "stick_action_interval":
            # 0 表示不随机动；其余至少 8 秒，避免一直手舞足蹈。
            return 0 if number <= 0 else min(max(number, 8), 600)
        return number
    if isinstance(default, float):
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        if key == "volume":
            return min(max(number, 0.0), 1.0)
        if key == "playback_rate":
            return min(max(number, 0.5), 2.0)
        if key == "opacity":
            return min(max(number, 0.3), 1.0)
        if key == "overlap_trigger_gap":
            return min(max(number, 0.0), 200.0)
        if key == "stick_body_ratio":
            return min(max(number, 0.4), 1.4)
        if key == "stick_line_width":
            return min(max(number, 2.0), 12.0)
        if key == "stick_neck_overlap":
            return min(max(number, 0.0), 40.0)
        return number
    if isinstance(default, str):
        if key in {"quiet_start", "quiet_end"}:
            from .quiet_hours import normalize_hhmm

            text = value if isinstance(value, str) else ""
            return normalize_hhmm(text, str(default))
        if key == "stick_spin_axis":
            return value if value in {"flip", "roll"} else default
        if key == "auto_move_dialog_mode":
            return value if value in {"crosstalk", "battle", "random"} else default
        if key in {"stick_color_lei", "stick_color_yu"}:
            text = value if isinstance(value, str) else ""
            return text if text.startswith("#") and len(text) in {4, 7, 9} else default
        return value
    return value


def load_config(path: Path) -> Config:
    """读取 JSON 配置，缺字段用默认值补全，非法值做 clamp，未知字段忽略。

    解析失败时把坏文件重命名为 ``.bak`` 并回退默认配置。绝不抛异常。
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config(**_defaults())  # type: ignore[arg-type]
    except (OSError, json.JSONDecodeError):
        _backup_bad_file(path)
        return Config(**_defaults())  # type: ignore[arg-type]

    if not isinstance(raw, dict):
        _backup_bad_file(path)
        return Config(**_defaults())  # type: ignore[arg-type]

    data: dict[str, object] = {}
    for key, default in DEFAULTS.items():
        if key in raw:
            data[key] = _coerce(key, raw[key])
        elif isinstance(default, list):
            data[key] = list(default)
        else:
            data[key] = default
    return Config(**data)  # type: ignore[arg-type]


def _backup_bad_file(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        if path.exists():
            os.replace(path, backup)
    except OSError:
        pass


def save_config(config: Config, path: Path) -> None:
    """把配置原子写入 JSON，仅写入白名单字段（DEFAULTS 的键）。"""
    path = Path(path)
    data = {key: getattr(config, key) for key in DEFAULTS}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
