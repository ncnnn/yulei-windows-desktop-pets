"""磨砂玻璃材质的决策与配色（纯逻辑，不导入 Qt，方便单测）。

**适用范围**：只有右键菜单、托盘菜单与设置窗口用磨砂；桌宠主窗口本身必须
**绝对透明**——除了大头与火柴人线条，其余像素全透明，能直接看到桌面。所以
这里不参与主窗口的任何绘制。

材质顺序：先尝试系统 Acrylic（``SetWindowCompositionAttribute``，Win10/11 都
有），失败再退化成自绘的半透明圆角底。降级时只降「模糊」，不降可读性——自绘
退化底的 alpha 更高，保证菜单文字在任何壁纸下都看得清。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 菜单与设置窗口的圆角半径（Windows 11 的菜单本身就是圆角，这两组数值与之接近）。
MENU_RADIUS = 10
DIALOG_RADIUS = 12
MIN_RADIUS = 0
MAX_RADIUS = 24

# 降级原因码，写进日志便于定位「磨砂没生效」。
REASON_OK = "ok"
REASON_DISABLED = "disabled"
REASON_NO_API = "no-acrylic-api"
REASON_NO_COMPOSITING = "no-compositing"
REASON_REMOTE = "remote-session"

REASON_LABELS = {
    REASON_OK: "系统磨砂已启用",
    REASON_DISABLED: "磨砂已关闭",
    REASON_NO_API: "系统不支持 Acrylic，已退化为自绘半透明",
    REASON_NO_COMPOSITING: "系统未开启透明效果，已退化为自绘半透明",
    REASON_REMOTE: "远程桌面会话，已退化为自绘半透明",
}


def clamp_radius(value: object) -> int:
    """把任意输入收敛成 0..MAX_RADIUS 的整数半径。"""
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DIALOG_RADIUS
    return min(max(number, MIN_RADIUS), MAX_RADIUS)


@dataclass(frozen=True, slots=True)
class FrostedPlan:
    """菜单/设置窗口要用的材质结论。"""

    enabled: bool
    acrylic: bool
    radius: int
    reason: str

    def describe(self) -> str:
        if not self.enabled:
            return "磨砂已关闭"
        if self.acrylic:
            return f"系统磨砂（圆角 {self.radius}px）"
        return f"自绘半透明（圆角 {self.radius}px，无系统模糊）"


DISABLED_PLAN = FrostedPlan(enabled=False, acrylic=False, radius=0, reason=REASON_DISABLED)


def plan_frosted(
    *,
    enabled: bool,
    radius: int = MENU_RADIUS,
    acrylic_available: bool = True,
    compositing: bool = True,
    remote: bool = False,
) -> FrostedPlan:
    """决定用系统 Acrylic 还是自绘退化底；两者都可读，差别只在模糊。"""
    if not enabled:
        return DISABLED_PLAN
    corner = clamp_radius(radius)
    if remote:
        return FrostedPlan(True, False, corner, REASON_REMOTE)
    if not compositing:
        return FrostedPlan(True, False, corner, REASON_NO_COMPOSITING)
    if not acrylic_available:
        return FrostedPlan(True, False, corner, REASON_NO_API)
    return FrostedPlan(True, True, corner, REASON_OK)


#: 系统 Acrylic 的着色（RGBA；平台层负责换算成 AABBGGRR）。
ACRYLIC_TINT = (26, 28, 36, 168)
#: 自绘退化底：比 Acrylic 更实一点，保证文字可读。
FALLBACK_TINT = (24, 26, 34, 236)
BORDER = (255, 255, 255, 46)
