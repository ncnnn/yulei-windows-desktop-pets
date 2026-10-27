"""半透明磨砂面板的样式决策（纯逻辑，不导入 Qt，方便单测）。

桌面宠物窗口是一块逐像素透明的分层窗口。系统级的 Acrylic / BlurBehind 会把
**整个窗口矩形**糊成一块玻璃：既盖掉圆角，也让原本「看不见也不吃点击」的
透明区域变成实心面板。所以这里不调用系统 API，而是由窗口层用 QPainter 画一块
半透明圆角面板，模糊观感用「顶部高光 + 中心柔光 + 细描边」表达。

这样做的好处是分辨率、缩放比例、浅色/深色壁纸、远程桌面下表现一致，而且
窗口标志（置顶、不抢焦点、鼠标穿透）一个都不动。

降级顺序按需求固定为：**点击功能 > 置顶 > 磨砂 > 圆角**：

1. 点击与置顶永不牺牲——面板只是画上去的，不碰 windowFlags；
2. 系统关闭透明效果、或处于远程桌面会话时，先丢掉磨砂层（模糊观感），
   保留半透明底与圆角，避免拖慢渲染；
3. 圆角只在面板太小时自动收窄，不会被丢弃。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 圆角半径的可选范围；0 表示直角（不画圆角）。
MIN_RADIUS = 0
MAX_RADIUS = 28
DEFAULT_RADIUS = 14

#: 面板在人物四周留出的视觉边距（像素，不随人物大小缩放）。
PANEL_PAD = 10

# 降级原因码：写进日志，便于用户反馈「磨砂没生效」时定位。
REASON_OK = "ok"
REASON_DISABLED = "disabled"
REASON_NO_COMPOSITING = "no-compositing"
REASON_REMOTE = "remote-session"

REASON_LABELS = {
    REASON_OK: "磨砂面板已启用",
    REASON_DISABLED: "面板已关闭",
    REASON_NO_COMPOSITING: "系统未开启透明效果，已降级为半透明面板",
    REASON_REMOTE: "远程桌面会话，已降级为半透明面板",
}


def clamp_radius(value: object) -> int:
    """把任意输入收敛成 0..MAX_RADIUS 的整数半径。"""
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_RADIUS
    return min(max(number, MIN_RADIUS), MAX_RADIUS)


def radius_for(width: float, height: float, radius: int) -> int:
    """按面板实际尺寸收窄半径：圆角不能超过短边的一半，否则会画成胶囊。"""
    limit = int(min(max(width, 0.0), max(height, 0.0)) // 2)
    return max(MIN_RADIUS, min(clamp_radius(radius), limit))


@dataclass(frozen=True, slots=True)
class GlassPlan:
    """绘制面板需要的全部结论；窗口层只按它执行，不再做判断。"""

    panel: bool
    frosted: bool
    radius: int
    reason: str

    @property
    def active(self) -> bool:
        return self.panel

    def describe(self) -> str:
        if not self.panel:
            return "面板已关闭"
        suffix = "磨砂" if self.frosted else "半透明（无磨砂）"
        return f"{suffix}面板，圆角 {self.radius}px"


DISABLED_PLAN = GlassPlan(panel=False, frosted=False, radius=0, reason=REASON_DISABLED)


def plan_glass(
    *,
    enabled: bool,
    radius: int,
    compositing: bool = True,
    remote: bool = False,
) -> GlassPlan:
    """决定画什么：关闭 / 磨砂 / 无磨砂半透明，但圆角始终保留。"""
    if not enabled:
        return DISABLED_PLAN
    corner = clamp_radius(radius)
    if remote:
        return GlassPlan(panel=True, frosted=False, radius=corner, reason=REASON_REMOTE)
    if not compositing:
        return GlassPlan(
            panel=True,
            frosted=False,
            radius=corner,
            reason=REASON_NO_COMPOSITING,
        )
    return GlassPlan(panel=True, frosted=True, radius=corner, reason=REASON_OK)
