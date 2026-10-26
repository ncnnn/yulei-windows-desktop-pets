"""Windows 开机自启管理（写入 Run 注册表项）。

仅 Windows 真正生效；其它系统所有公开函数安全返回（no-op）。所有 ``winreg`` 访问都被
``try/except`` 包裹，绝不向调用方抛出未处理异常。测试通过 monkeypatch ``autostart.winreg``
为 mock 进入 Windows 分支，不会真正写入注册表。
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows
    winreg = None  # type: ignore[assignment]

APP_NAME = "LeiYuDesktopPets"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LeiYuDesktopPets"


def _command(exe_path: Path) -> str:
    """返回用于自启的 ``cmd /c start`` 命令（路径含空格时双引号包裹）。"""
    exe_path = Path(exe_path)
    return f'cmd /c start "" /D "{exe_path.parent}" "{exe_path}"'


def is_enabled(exe_path: Path | None = None) -> bool:
    """Run 项中是否存在指向本程序的自启值。非 Windows 始终返回 False。"""
    if winreg is None:
        return False
    target = Path(exe_path or sys.executable)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:  # type: ignore[arg-type]
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)  # type: ignore[attr-defined]
    except OSError:
        return False
    if not isinstance(value, str):
        return False
    return target.name in value


def set_enabled(enabled: bool, exe_path: Path | None = None) -> bool:
    """启用/禁用开机自启；启用后回读验证，失败返回 False。禁用时键不存在也返回 True。"""
    if winreg is None:
        return False
    target = Path(exe_path or sys.executable)
    try:
        if enabled:
            command = _command(target)
            with winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
                REG_KEY,
                0,
                winreg.KEY_SET_VALUE,  # type: ignore[attr-defined]
            ) as key:
                winreg.SetValueEx(  # type: ignore[attr-defined]
                    key, VALUE_NAME, 0, winreg.REG_SZ, command  # type: ignore[attr-defined]
                )
            return is_enabled(target)
        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
            REG_KEY,
            0,
            winreg.KEY_SET_VALUE,  # type: ignore[attr-defined]
        ) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)  # type: ignore[attr-defined]
            except OSError:
                pass
        return True
    except OSError:
        return False


def remove(exe_path: Path | None = None) -> None:
    """删除自启注册表值（等价 set_enabled(False)）。"""
    set_enabled(False, exe_path)


def self_check_requested_but_missing(config_autostart: bool, exe_path: Path | None = None) -> bool:
    """配置要求自启但实际未启用时返回 True（用于提醒自启被安全软件清理）。"""
    return bool(config_autostart) and not is_enabled(exe_path)
