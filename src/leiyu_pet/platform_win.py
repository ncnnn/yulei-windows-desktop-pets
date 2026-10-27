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

#: SetWindowCompositionAttribute 的 AccentPolicy 属性号与状态值。
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
#: DwmSetWindowAttribute：Win11 的窗口圆角偏好。
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
#: Acrylic 需要 Win10 1803（build 17134）以上。
MIN_ACRYLIC_BUILD = 17134

#: 命中测试消息：透明像素返回 HTTRANSPARENT，事件直接交给下层窗口。
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTTRANSPARENT = -1


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


def _accent_types():
    """构造 Acrylic 需要的 ctypes 结构（只构造一次）。"""
    import ctypes
    from ctypes import wintypes

    class AccentPolicy(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
        ]

    class WindowCompositionAttributeData(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    return AccentPolicy, WindowCompositionAttributeData, wintypes


def acrylic_available() -> bool:
    """系统是否具备 Acrylic 能力（Win10 1803+ 且导出该 API）。"""
    if not on_windows():
        return False
    try:
        import ctypes
        import sys

        if sys.getwindowsversion().build < MIN_ACRYLIC_BUILD:  # type: ignore[attr-defined]
            return False
        return hasattr(ctypes.windll.user32, "SetWindowCompositionAttribute")  # type: ignore[attr-defined]
    except Exception:
        return False


def _accent_color(tint: tuple[int, int, int, int]) -> int:
    """RGBA → Acrylic 需要的 AABBGGRR。"""
    red, green, blue, alpha = (max(0, min(255, int(v))) for v in tint)
    return (alpha << 24) | (blue << 16) | (green << 8) | red


def set_acrylic(hwnd: int, tint: tuple[int, int, int, int]) -> bool:
    """给普通窗口（菜单/对话框）加系统磨砂；失败返回 False，由调用方退化。"""
    if not on_windows() or not hwnd:
        return False
    try:
        import ctypes

        accent_cls, data_cls, _wintypes = _accent_types()
        data = data_cls()
        policy = accent_cls()
        policy.AccentFlags = 2
        policy.GradientColor = _accent_color(tint)
        data.Attribute = WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent_cls)
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        for state in (ACCENT_ENABLE_ACRYLICBLURBEHIND, ACCENT_ENABLE_BLURBEHIND):
            policy.AccentState = state
            data.Data = ctypes.cast(ctypes.byref(policy), ctypes.c_void_p)
            if user32.SetWindowCompositionAttribute(int(hwnd), ctypes.byref(data)):
                return True
        return False
    except Exception:
        return False


def clear_acrylic(hwnd: int) -> bool:
    """撤掉磨砂（切换开关或窗口销毁前调用）。"""
    if not on_windows() or not hwnd:
        return False
    try:
        import ctypes

        accent_cls, data_cls, _wintypes = _accent_types()
        policy = accent_cls()
        policy.AccentState = ACCENT_DISABLED
        data = data_cls()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(policy), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent_cls)
        ctypes.windll.user32.SetWindowCompositionAttribute(  # type: ignore[attr-defined]
            int(hwnd), ctypes.byref(data)
        )
        return True
    except Exception:
        return False


def _msg_struct():
    """MSG 结构（只构造一次）；字段顺序必须与 winuser.h 一致。"""
    import ctypes
    from ctypes import wintypes

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", ctypes.c_size_t),
            ("lParam", ctypes.c_ssize_t),
            ("time", wintypes.DWORD),
            ("pt_x", wintypes.LONG),
            ("pt_y", wintypes.LONG),
            ("lPrivate", wintypes.DWORD),
        ]

    return MSG


def nchittest_point(message_ptr: int) -> tuple[int, int] | None:
    """从 ``WM_NCHITTEST`` 的 MSG 指针里取出光标屏幕坐标。

    不是这条消息、非 Windows、或指针无效时返回 ``None``，调用方据此交回 Qt
    默认处理，避免把正常消息吞掉。
    """
    if not on_windows() or not message_ptr:
        return None
    try:
        import ctypes

        msg = _msg_struct().from_address(int(message_ptr))
        if msg.message != WM_NCHITTEST:
            return None
        lparam = int(msg.lParam)
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        return (x, y)
    except Exception:
        return None


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """窗口在屏幕上的**物理像素**矩形 ``(left, top, right, bottom)``。

    ``WM_NCHITTEST`` 的 lParam 是物理像素，Qt 的坐标却是逻辑像素；要把命中点
    换算回窗口局部坐标，必须以这个矩形为准（见 ``PetWindow._native_to_local``）。
    无边框 + 去投影的窗口没有 DWM 边框，矩形与实际绘制区域完全一致。

    取不到（非 Windows、句柄无效、窗口已销毁）时返回 ``None``，调用方回退到
    Qt 的 ``devicePixelRatioF`` 换算。
    """
    if not on_windows() or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        rect = RECT()
        if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def round_corners(hwnd: int) -> bool:
    """Win11：让系统把窗口边框画成圆角（旧系统静默失败）。"""
    if not on_windows() or not hwnd:
        return False
    try:
        import ctypes

        preference = ctypes.c_int(DWMWCP_ROUND)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(  # type: ignore[attr-defined]
            int(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return result == 0
    except Exception:
        return False


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
