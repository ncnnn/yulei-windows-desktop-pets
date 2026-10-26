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
    "version": 2,
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
}


@dataclass(slots=True)
class Config:
    version: int = 2
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
        return number
    if isinstance(default, float):
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        if key == "volume":
            return min(max(number, 0.0), 1.0)
        return number
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
