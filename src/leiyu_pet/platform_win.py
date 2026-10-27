"""Windows 平台相关的窗口几何工具。

仅 Windows 真正生效；其它系统函数直接返回安全占位值。所有 PySide6 导入都在函数内局部进行，
避免非 GUI（或无 Qt）的单元测试触发 Qt 初始化。运行时调用 ``keep_window_on_screen`` 防止窗口
跑到屏幕外。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QRect

DEFAULT_FALLBACK_GEOMETRY = (0, 0, 1280, 720)
MIN_VISIBLE_AREA = 80
#: GetSystemMetrics 的「当前是远程桌面会话」索引。
SM_REMOTESESSION = 0x1000


def on_windows() -> bool:
    """当前是否运行在 Windows。"""
    return os.name == "nt"


def display_capabilities() -> tuple[bool, bool]:
    """返回 ``(是否开启桌面合成/透明效果, 是否远程桌面会话)``。

    只用于决定「磨砂层画不画」这类纯观感选择，所以任何异常都退化为
    ``(True, False)``——宁可多画一层，也不要因为探测失败让面板变样。
    """
    if not on_windows():
        return (True, False)
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        remote = bool(user32.GetSystemMetrics(SM_REMOTESESSION))
    except Exception:
        return (True, False)

    compositing = True
    try:
        import ctypes

        enabled = ctypes.c_int(0)
        dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
        result = dwmapi.DwmIsCompositionEnabled(ctypes.byref(enabled))
        compositing = result == 0 and bool(enabled.value)
    except Exception:
        compositing = True
    return (compositing, remote)


def primary_working_area() -> tuple[int, int, int, int]:
    """返回主屏 availableGeometry 的 ``(x, y, w, h)``；非 Windows 返回占位值。"""
    if not on_windows():
        return DEFAULT_FALLBACK_GEOMETRY
    try:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return DEFAULT_FALLBACK_GEOMETRY
        area = screen.availableGeometry()
        return (area.x(), area.y(), area.width(), area.height())
    except Exception:
        return DEFAULT_FALLBACK_GEOMETRY


def _intersection_size(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int]:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ox = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    oy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return (ox, oy)


def keep_window_on_screen(geometry: QRect) -> QRect:
    """把窗口几何夹到任意可见屏的可用区域内，保证至少与某屏交集不小于 80x80。

    非 Windows 原样返回。若所有屏幕均无法满足最小可见区域，则回退到主屏。
    """
    if not on_windows():
        return geometry

    try:
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        if not screens:
            return geometry

        g = (geometry.x(), geometry.y(), geometry.width(), geometry.height())
        candidates = []
        for screen in screens:
            area = screen.availableGeometry()
            rect = (area.x(), area.y(), area.width(), area.height())
            iw, ih = _intersection_size(g, rect)
            if iw >= MIN_VISIBLE_AREA and ih >= MIN_VISIBLE_AREA:
                candidates.append(rect)

        if not candidates:
            area = screens[0].availableGeometry()
            candidates.append((area.x(), area.y(), area.width(), area.height()))

        target = candidates[0]
        aw, ah = target[2], target[3]
        x = max(target[0], min(geometry.x(), target[0] + aw - geometry.width()))
        y = max(target[1], min(geometry.y(), target[1] + ah - geometry.height()))
        return QRect(x, y, geometry.width(), geometry.height())
    except Exception:
        return geometry
