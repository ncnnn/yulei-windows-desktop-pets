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
from dataclasses import dataclass
from pathlib import Path

DEFAULTS: dict[str, object] = {
    "version": 1,
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
}


@dataclass(slots=True)
class Config:
    version: int = 1
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


def _coerce(key: str, value: object) -> object:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        if key == "version":
            return number if number >= 1 else 1
        if key == "distance":
            return min(max(number, 0), 100)
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
        return Config(**DEFAULTS)  # type: ignore[arg-type]
    except (OSError, json.JSONDecodeError):
        _backup_bad_file(path)
        return Config(**DEFAULTS)  # type: ignore[arg-type]

    if not isinstance(raw, dict):
        _backup_bad_file(path)
        return Config(**DEFAULTS)  # type: ignore[arg-type]

    data: dict[str, object] = {}
    for key, default in DEFAULTS.items():
        if key in raw:
            data[key] = _coerce(key, raw[key])
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
