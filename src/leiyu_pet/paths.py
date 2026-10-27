"""应用数据目录与关键路径解析。

纯逻辑模块，不依赖 Qt，便于单元测试。所有返回路径在语义要求时保证目录存在。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "LeiYuDesktopPets"


def exe_dir() -> Path:
    """返回可执行文件所在目录。

    冻结后（PyInstaller 等）``sys.executable`` 即 exe 路径；源码运行回退到本模块所在目录。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_portable() -> bool:
    """存在 ``<exe_dir>/portable.ini`` 视为便携版。"""
    return (exe_dir() / "portable.ini").is_file()


def _appdata_dir() -> Path:
    """返回应用数据根。

    优先 ``APPDATA``（Windows 安装版通常已设置），缺失时回退 ``LOCALAPPDATA``，
    再缺失则回退系统临时目录。返回前不创建目录（由 ``base_dir`` 负责）。
    """
    for name in ("APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(name)
        if value:
            return Path(value)
    return Path(tempfile.gettempdir())


def base_dir() -> Path:
    """返回应用数据根目录，并确保其存在。

    便携版：``<exe_dir>/data``；安装版：``<AppData>/<APP_NAME>``。
    """
    directory = exe_dir() / "data" if is_portable() else _appdata_dir() / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def config_path() -> Path:
    """返回配置文件路径。"""
    return base_dir() / "config.json"


def assets_dir() -> Path:
    """返回随包素材目录；不存在则回退到导入素材存放目录。

    查找顺序：``<exe_dir>/assets``（需同时含 ``lei.png`` 与 ``yu.png`` 视为随包素材），
    否则 ``<base_dir>/assets``（导入素材存放处）。返回前确保目录存在。
    """
    bundled = exe_dir() / "assets"
    if bundled.is_dir() and (bundled / "lei.png").is_file() and (bundled / "yu.png").is_file():
        bundled.mkdir(parents=True, exist_ok=True)
        return bundled
    imported = base_dir() / "assets"
    imported.mkdir(parents=True, exist_ok=True)
    return imported


def assets_store_dir() -> Path:
    """返回素材导入时的 store 目录，并确保其存在。"""
    store = base_dir() / "assets"
    store.mkdir(parents=True, exist_ok=True)
    return store


def log_path() -> Path:
    """返回日志文件路径。"""
    return base_dir() / "pet.log"


def app_icon_path() -> Path | None:
    """返回产品图标（.ico）；找不到时返回 ``None``，调用方回退系统图标。

    冻结态由打包脚本放到 ``_MEIPASS/assets/app.ico``；源码运行取仓库里的
    ``packaging/app.ico``；便携版还允许放在 exe 同级 ``assets`` 目录。
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "app.ico")
    candidates.append(Path(__file__).resolve().parents[2] / "packaging" / "app.ico")
    candidates.append(exe_dir() / "assets" / "app.ico")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
