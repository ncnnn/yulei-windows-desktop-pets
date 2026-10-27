"""Windows 全局热键（RegisterHotKey），非 Windows 平台静默降级。

设计取舍：
* 用 ``QAbstractNativeEventFilter`` 接 ``WM_HOTKEY``，不额外起线程；
* 注册失败（被其它程序占用）不影响主程序，只是少了快捷键；
* 解析逻辑是纯函数，便于在无窗口环境测试。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Literal

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

HotkeyAction = Literal["toggle_visible", "crosstalk", "random_line", "mute", "stop"]

#: 默认绑定：显示/隐藏、相声模式、随机一句、捂嘴、停止播放。
DEFAULT_BINDINGS: dict[str, str] = {
    "toggle_visible": "ctrl+alt+h",
    "crosstalk": "ctrl+alt+k",
    "random_line": "ctrl+alt+r",
    "mute": "ctrl+alt+m",
    "stop": "ctrl+alt+x",
}

ACTION_LABELS: dict[str, str] = {
    "toggle_visible": "显示/隐藏桌宠",
    "crosstalk": "相声模式",
    "random_line": "随机说一段",
    "mute": "捂嘴（禁言）",
    "stop": "停止播放",
}

_MODIFIER_ALIASES = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "cmd": MOD_WIN,
    "super": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}


class HotkeyError(ValueError):
    """无法解析的热键描述。"""


def parse_binding(spec: str) -> tuple[int, int]:
    """把 ``"ctrl+alt+h"`` 解析为 ``(modifiers, virtual_key)``。

    至少需要一个修饰键，避免吞掉普通按键。
    """
    parts = [part.strip().lower() for part in str(spec).split("+") if part.strip()]
    if not parts:
        raise HotkeyError(f"空热键：{spec!r}")

    modifiers = 0
    key_token = ""
    for part in parts:
        if part in _MODIFIER_ALIASES:
            modifiers |= _MODIFIER_ALIASES[part]
        else:
            key_token = part
    if not key_token:
        raise HotkeyError(f"缺少主键：{spec!r}")
    if modifiers == 0:
        raise HotkeyError(f"缺少修饰键：{spec!r}")

    if len(key_token) == 1 and key_token.isalnum():
        virtual_key = ord(key_token.upper())
    elif key_token in _NAMED_KEYS:
        virtual_key = _NAMED_KEYS[key_token]
    elif key_token.startswith("f") and key_token[1:].isdigit():
        number = int(key_token[1:])
        if not 1 <= number <= 24:
            raise HotkeyError(f"功能键超出范围：{spec!r}")
        virtual_key = 0x70 + number - 1
    else:
        raise HotkeyError(f"无法识别的主键：{spec!r}")
    return modifiers, virtual_key


def describe_binding(spec: str) -> str:
    """把 ``ctrl+alt+h`` 渲染成 ``Ctrl+Alt+H`` 供界面显示。"""
    labels: list[str] = []
    for part in (item.strip() for item in str(spec).split("+")):
        if not part:
            continue
        labels.append(part.upper() if len(part) == 1 else part.title())
    return "+".join(labels)


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: HotkeyManager) -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt 命名
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        except Exception:
            return False, 0
        if msg.message == WM_HOTKEY:
            self._owner._dispatch(int(msg.wParam))
            return True, 0
        return False, 0


class HotkeyManager(QObject):
    """注册/注销全局热键；触发时发出动作名。"""

    triggered = Signal(str)

    def __init__(self, bindings: dict[str, str] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bindings = dict(bindings or DEFAULT_BINDINGS)
        self._filter = _HotkeyFilter(self)
        self._installed = False
        self._ids: dict[int, str] = {}
        self._failed: dict[str, str] = {}

    @property
    def failed(self) -> dict[str, str]:
        """注册失败的动作 → 原因，便于界面提示。"""
        return dict(self._failed)

    def install(self, app: QCoreApplication | None = None) -> int:
        """注册全部热键，返回成功数量。非 Windows 或失败时返回 0。"""
        if sys.platform != "win32" or self._installed:
            return 0
        application = app or QCoreApplication.instance()
        if application is None:
            return 0
        application.installNativeEventFilter(self._filter)
        self._installed = True
        registered = 0
        for index, action in enumerate(self.bindings, start=1):
            try:
                modifiers, virtual_key = parse_binding(self.bindings[action])
            except HotkeyError as exc:
                self._failed[action] = str(exc)
                continue
            ok = ctypes.windll.user32.RegisterHotKey(  # type: ignore[attr-defined]
                None, index, modifiers | MOD_NOREPEAT, virtual_key
            )
            if ok:
                self._ids[index] = action
                registered += 1
            else:
                self._failed[action] = "热键已被其它程序占用"
        if registered == 0:
            self.uninstall()
        return registered

    def uninstall(self) -> None:
        if not self._installed:
            return
        application = QCoreApplication.instance()
        for hotkey_id in list(self._ids):
            ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)  # type: ignore[attr-defined]
        self._ids.clear()
        if application is not None:
            application.removeNativeEventFilter(self._filter)
        self._installed = False

    def _dispatch(self, hotkey_id: int) -> None:
        action = self._ids.get(hotkey_id)
        if action is not None:
            self.triggered.emit(action)
