"""火柴人躯体的纯逻辑：关节坐标与动作状态机（不导入 Qt）。

坐标系：原点在**颈部挂点**，``y`` 向下为正，``1.0`` 等于躯体总高度。
渲染层只需 ``px = cx + x * unit``、``py = neck_y + y * unit`` 即可，因此这套
数学完全不依赖分辨率，改窗口大小不用重算任何素材。

状态机只有一条规则：``wave`` / ``dance`` / ``jump`` 是**一次性动作**，播完
自动回到 ``idle``；``idle`` / ``drag`` / ``spin_360`` 是持续状态，由调用方
显式切换。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]

IDLE = "idle"
WAVE = "wave"
DANCE = "dance"
JUMP = "jump"
SPIN = "spin_360"
DRAG = "drag"
#: 2.1.1 新增的十款动作，轮廓互不相似（合掌/拉伸/弯腰/托腮/跑/睡/踢/蹲/比心/敬礼）。
CLAP = "clap"
STRETCH = "stretch"
BOW = "bow"
THINK = "think"
RUN = "run"
SLEEP = "sleep"
KICK = "kick"
SQUAT = "squat"
HEART = "heart"
SALUTE = "salute"

#: 中文名，用于右键「动作」菜单与日志。
ACTION_LABELS = {
    IDLE: "待机",
    WAVE: "招手",
    DANCE: "跳舞",
    JUMP: "跳跃",
    SPIN: "转身",
    DRAG: "被拎起",
    CLAP: "鼓掌",
    STRETCH: "伸懒腰",
    BOW: "鞠躬",
    THINK: "托腮",
    RUN: "原地跑",
    SLEEP: "打瞌睡",
    KICK: "踢腿",
    SQUAT: "深蹲",
    HEART: "比心",
    SALUTE: "敬礼",
}

TIMED_STATES = frozenset(
    {
        WAVE,
        DANCE,
        JUMP,
        CLAP,
        STRETCH,
        BOW,
        THINK,
        RUN,
        SLEEP,
        KICK,
        SQUAT,
        HEART,
        SALUTE,
    }
)

#: 随机动作池：一次性动作都在里面，不含 drag/spin 这类由交互驱动的状态。
RANDOM_ACTIONS = (
    WAVE,
    DANCE,
    CLAP,
    STRETCH,
    BOW,
    THINK,
    RUN,
    SLEEP,
    KICK,
    SQUAT,
    HEART,
    SALUTE,
)

#: 各关节在归一化空间里的位置。手臂/腿部各两段。
SHOULDER_Y = 0.10
SHOULDER_X = 0.17
HIP_Y = 0.52
HIP_X = 0.10
KNEE_Y = 0.76
FOOT_Y = 1.0
UPPER_ARM = 0.17
FOREARM = 0.17
THIGH = 0.24
SHIN = 0.24

BREATHE_PERIOD = 2.8
#: 躯干相对窗口的最大倾角（拖拽时像被拎起来）。
MAX_LEAN = 0.28


def _rotate(point: Point, angle: float, pivot: Point) -> Point:
    """把 point 绕 pivot 旋转 angle 弧度。"""
    if not angle:
        return point
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - pivot[0], point[1] - pivot[1]
    return (
        pivot[0] + dx * cos_a - dy * sin_a,
        pivot[1] + dx * sin_a + dy * cos_a,
    )


@dataclass(frozen=True, slots=True)
class Limb:
    """一条两段肢体：起点（肩/髋）、关节（肘/膝）、末端（手/脚）。"""

    start: Point
    joint: Point
    end: Point


@dataclass(frozen=True, slots=True)
class StickPose:
    neck: Point
    hip: Point
    arms: tuple[Limb, Limb]
    legs: tuple[Limb, Limb]
    lean: float = 0.0

    def rotated(self) -> StickPose:
        """按 lean 绕脚底中心整体倾斜，返回最终姿态。"""
        if not self.lean:
            return self
        pivot = (self.neck[0], FOOT_Y)
        return StickPose(
            neck=_rotate(self.neck, self.lean, pivot),
            hip=_rotate(self.hip, self.lean, pivot),
            arms=tuple(
                Limb(
                    _rotate(arm.start, self.lean, pivot),
                    _rotate(arm.joint, self.lean, pivot),
                    _rotate(arm.end, self.lean, pivot),
                )
                for arm in self.arms
            ),  # type: ignore[arg-type]
            legs=tuple(
                Limb(
                    _rotate(leg.start, self.lean, pivot),
                    _rotate(leg.joint, self.lean, pivot),
                    _rotate(leg.end, self.lean, pivot),
                )
                for leg in self.legs
            ),  # type: ignore[arg-type]
            lean=self.lean,
        )


def idle_legs(phase: float) -> tuple[Limb, Limb]:
    """待机腿部：双脚略分开，静止时也有极缓的重心移动。"""
    sway = 0.004 * math.sin(2.0 * math.pi * phase / BREATHE_PERIOD)
    return (
        Limb(
            (-HIP_X, HIP_Y),
            (-(HIP_X + 0.03), KNEE_Y),
            (-(HIP_X + 0.05 + sway), FOOT_Y),
        ),
        Limb(
            (HIP_X, HIP_Y),
            (HIP_X + 0.03, KNEE_Y),
            (HIP_X + 0.05 - sway, FOOT_Y),
        ),
    )


def idle_pose(phase: float) -> StickPose:
    """待机：身体呼吸起伏 + 手臂轻微摆动，手臂略向外张。"""
    breathe = math.sin(2.0 * math.pi * phase / BREATHE_PERIOD)
    shoulder_y = SHOULDER_Y + 0.006 * breathe
    shoulder_x = SHOULDER_X
    hip = (0.0, HIP_Y)
    arms = tuple(
        Limb(
            (side * shoulder_x, shoulder_y),
            (side * (shoulder_x + 0.05), shoulder_y + UPPER_ARM),
            (side * (shoulder_x + 0.08 + 0.008 * breathe), shoulder_y + UPPER_ARM + FOREARM),
        )
        for side in (-1.0, 1.0)
    )
    return StickPose(neck=(0.0, 0.0), hip=hip, arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


def wave_pose(phase: float, progress: float) -> StickPose:
    """招手：右手抬起并左右摆，抬起幅度随 progress 升起。"""
    base = idle_pose(phase)
    lift = min(1.0, max(0.0, progress))
    swing = math.sin(phase * 9.0) * 0.05 * lift
    right = Limb(
        (SHOULDER_X, SHOULDER_Y),
        (SHOULDER_X + 0.10 * lift, SHOULDER_Y - 0.06 * lift),
        (SHOULDER_X + 0.17 * lift + swing, SHOULDER_Y - 0.22 * lift),
    )
    return StickPose(
        neck=base.neck,
        hip=base.hip,
        arms=(base.arms[0], right),
        legs=base.legs,
    )


def dance_pose(phase: float) -> StickPose:
    """跳舞：双臂上下交替、胯部左右摆、双脚轮流抬。"""
    beat = math.sin(phase * 7.0)
    sway = 0.03 * beat
    hip = (sway, HIP_Y)
    arms = (
        Limb(
            (-SHOULDER_X, SHOULDER_Y),
            (-(SHOULDER_X + 0.10), SHOULDER_Y - 0.05 * beat),
            (-(SHOULDER_X + 0.16), SHOULDER_Y - 0.18 - 0.06 * beat),
        ),
        Limb(
            (SHOULDER_X, SHOULDER_Y),
            (SHOULDER_X + 0.10, SHOULDER_Y + 0.05 * beat),
            (SHOULDER_X + 0.16, SHOULDER_Y - 0.18 + 0.06 * beat),
        ),
    )
    legs = (
        Limb(
            (-HIP_X + sway, HIP_Y),
            (-(HIP_X + 0.04), KNEE_Y),
            (-(HIP_X + 0.05), FOOT_Y - 0.05 * max(0.0, beat)),
        ),
        Limb(
            (HIP_X + sway, HIP_Y),
            (HIP_X + 0.04, KNEE_Y),
            (HIP_X + 0.05, FOOT_Y - 0.05 * max(0.0, -beat)),
        ),
    )
    return StickPose(neck=(sway * 0.5, 0.0), hip=hip, arms=arms, legs=legs)


def jump_pose(phase: float) -> StickPose:
    """跳跃：收腿、双臂上举。"""
    arms = tuple(
        Limb(
            (side * SHOULDER_X, SHOULDER_Y),
            (side * (SHOULDER_X + 0.10), SHOULDER_Y - 0.10),
            (side * (SHOULDER_X + 0.14), SHOULDER_Y - 0.24),
        )
        for side in (-1.0, 1.0)
    )
    legs = tuple(
        Limb(
            (side * HIP_X, HIP_Y),
            (side * (HIP_X + 0.03), KNEE_Y - 0.12),
            (side * (HIP_X + 0.05), FOOT_Y - 0.24),
        )
        for side in (-1.0, 1.0)
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=legs)  # type: ignore[arg-type]


def drag_pose(phase: float) -> StickPose:
    """被拖动：双手上举像被拎着，双腿自然下垂并轻微摆动。"""
    swing = math.sin(phase * 5.0) * 0.04
    arms = tuple(
        Limb(
            (side * SHOULDER_X, SHOULDER_Y),
            (side * (SHOULDER_X + 0.06), SHOULDER_Y - 0.12),
            (side * (SHOULDER_X + 0.08), SHOULDER_Y - 0.26),
        )
        for side in (-1.0, 1.0)
    )
    legs = tuple(
        Limb(
            (side * HIP_X, HIP_Y),
            (side * (HIP_X + 0.02 + swing), KNEE_Y),
            (side * (HIP_X + 0.04 + swing * 1.6), FOOT_Y),
        )
        for side in (-1.0, 1.0)
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=legs)  # type: ignore[arg-type]


# --------------------------------------------------------------- 十款动作
# 每个姿势只改关节坐标，不改渲染层；neck 恒为 (0,0)——它是头部挂点，
# 动了就等于整个人平移，所以「弯腰/低头」都靠髋部与肩部的偏移表达。


def clap_pose(phase: float) -> StickPose:
    """鼓掌：双手在胸前开合，节拍快于呼吸。"""
    beat = 0.5 + 0.5 * math.sin(phase * 12.0)
    gap = 0.015 + 0.075 * beat
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.10, 0.24), (-gap, 0.29)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.10, 0.24), (gap, 0.29)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


def stretch_pose(phase: float) -> StickPose:
    """伸懒腰：双臂越过肩线向上拉伸，身体微微后仰，双腿并拢。"""
    sway = 0.03 * math.sin(phase * 2.2)
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.24, -0.04), (-0.20 + sway, -0.26)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.24, -0.04), (0.20 + sway, -0.26)),
    )
    legs = (
        Limb((-HIP_X, HIP_Y + 0.02), (-0.09, KNEE_Y), (-0.08, FOOT_Y)),
        Limb((HIP_X, HIP_Y + 0.02), (0.09, KNEE_Y), (0.08, FOOT_Y)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y + 0.02), arms=arms, legs=legs)


def bow_pose(phase: float) -> StickPose:
    """鞠躬：髋部后移形成斜的上身，双手垂到身前。"""
    bend = 0.5 - 0.5 * math.cos(phase * 2.4)
    hip_x = 0.20 * bend
    arms = (
        Limb(
            (-SHOULDER_X, SHOULDER_Y),
            (-0.10, 0.30 + 0.08 * bend),
            (-0.13, 0.44 + 0.12 * bend),
        ),
        Limb(
            (SHOULDER_X, SHOULDER_Y),
            (0.10, 0.30 + 0.08 * bend),
            (0.13, 0.44 + 0.12 * bend),
        ),
    )
    return StickPose(neck=(0.0, 0.0), hip=(hip_x, HIP_Y), arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


def think_pose(phase: float) -> StickPose:
    """托腮：一只手折到下巴附近，另一只垂下，肩膀随思考轻微起伏。"""
    bob = 0.01 * math.sin(phase * 1.6)
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.18, 0.30), (-0.16, 0.46)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.24, 0.30), (0.06, 0.10 + bob)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


def run_pose(phase: float) -> StickPose:
    """原地跑：双腿轮流抬膝，双臂反向摆动。"""
    swing = math.sin(phase * 8.0)
    arms = (
        Limb(
            (-SHOULDER_X, SHOULDER_Y),
            (-0.10 - 0.10 * swing, 0.24),
            (-0.08 - 0.20 * swing, 0.34),
        ),
        Limb(
            (SHOULDER_X, SHOULDER_Y),
            (0.10 + 0.10 * swing, 0.24),
            (0.08 + 0.20 * swing, 0.34),
        ),
    )
    legs = (
        Limb(
            (-HIP_X, HIP_Y),
            (-0.14 - 0.04 * max(0.0, swing), 0.68 - 0.14 * max(0.0, swing)),
            (-0.18, 0.92 - 0.20 * max(0.0, swing)),
        ),
        Limb(
            (HIP_X, HIP_Y),
            (0.14 + 0.04 * max(0.0, -swing), 0.68 - 0.14 * max(0.0, -swing)),
            (0.18, 0.92 - 0.20 * max(0.0, -swing)),
        ),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=legs)


def sleep_pose(phase: float) -> StickPose:
    """打瞌睡：上身塌下去、双手垂到身侧，配合很慢的点头节奏。"""
    nod = 0.02 * math.sin(phase * 1.1)
    shoulder_y = SHOULDER_Y + 0.12 + nod
    arms = (
        Limb((-SHOULDER_X, shoulder_y), (-0.10, 0.36), (-0.08, 0.52)),
        Limb((SHOULDER_X, shoulder_y), (0.10, 0.36), (0.08, 0.52)),
    )
    legs = (
        Limb((-HIP_X, HIP_Y + 0.04), (-0.08, KNEE_Y), (-0.16, FOOT_Y)),
        Limb((HIP_X, HIP_Y + 0.04), (0.08, KNEE_Y), (0.16, FOOT_Y)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.03, HIP_Y + 0.04), arms=arms, legs=legs)


def kick_pose(phase: float) -> StickPose:
    """踢腿：右腿前踢并收回，双臂外展保持平衡。"""
    swing = math.sin(phase * 7.5)
    lift = max(0.0, swing)
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.24, 0.20), (-0.30, 0.10)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.24, 0.20), (0.30, 0.10)),
    )
    legs = (
        Limb((-HIP_X, HIP_Y), (-0.09, KNEE_Y), (-0.08, FOOT_Y)),
        Limb(
            (HIP_X, HIP_Y),
            (0.14 + 0.16 * lift, KNEE_Y - 0.16 * lift),
            (0.16 + 0.34 * lift, FOOT_Y - 0.38 * lift),
        ),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=legs)


def squat_pose(phase: float) -> StickPose:
    """深蹲：髋部下沉、膝盖外撇，双臂平举在前。"""
    depth = 0.5 - 0.5 * math.cos(phase * 2.6)
    hip_y = HIP_Y + 0.12 * depth
    shoulder_y = SHOULDER_Y + 0.06 * depth
    arms = (
        Limb((-SHOULDER_X, shoulder_y), (-0.18, 0.22 + 0.06 * depth), (-0.16, 0.32 + 0.06 * depth)),
        Limb((SHOULDER_X, shoulder_y), (0.18, 0.22 + 0.06 * depth), (0.16, 0.32 + 0.06 * depth)),
    )
    legs = (
        Limb((-HIP_X - 0.04 * depth, hip_y), (-0.10 - 0.20 * depth, KNEE_Y - 0.02), (-0.12, FOOT_Y)),
        Limb((HIP_X + 0.04 * depth, hip_y), (0.10 + 0.20 * depth, KNEE_Y - 0.02), (0.12, FOOT_Y)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, hip_y), arms=arms, legs=legs)


def heart_pose(phase: float) -> StickPose:
    """比心：双手举过头顶在中间合拢，随心跳轻微起伏。"""
    pulse = 0.012 * math.sin(phase * 3.0)
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.16, -0.02 - pulse), (-0.02, -0.20 - pulse)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.16, -0.02 - pulse), (0.02, -0.20 - pulse)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


def salute_pose(phase: float) -> StickPose:
    """敬礼：右手抬到额前，左臂垂直贴身。"""
    twitch = 0.004 * math.sin(phase * 4.0)
    arms = (
        Limb((-SHOULDER_X, SHOULDER_Y), (-0.12, 0.28), (-0.10, 0.44)),
        Limb((SHOULDER_X, SHOULDER_Y), (0.34, 0.06), (0.05, 0.0 + twitch)),
    )
    return StickPose(neck=(0.0, 0.0), hip=(0.0, HIP_Y), arms=arms, legs=idle_legs(phase))  # type: ignore[arg-type]


#: 动作 → 姿势函数；没有映射的状态回落到待机。
POSE_BUILDERS = {
    IDLE: idle_pose,
    DANCE: dance_pose,
    JUMP: jump_pose,
    DRAG: drag_pose,
    CLAP: clap_pose,
    STRETCH: stretch_pose,
    BOW: bow_pose,
    THINK: think_pose,
    RUN: run_pose,
    SLEEP: sleep_pose,
    KICK: kick_pose,
    SQUAT: squat_pose,
    HEART: heart_pose,
    SALUTE: salute_pose,
}


# ------------------------------------------------------------- 线条命中
# 主窗口没有底板，点击判定必须落在「画出来的线条」上。这里用骨架线段做
# 点到线段的距离判定，容差按线宽放大，视觉与手感才对得上。


def segments(pose: StickPose) -> tuple[tuple[Point, Point], ...]:
    """骨架的所有线段：躯干 + 每条肢体的两节。"""
    lines: list[tuple[Point, Point]] = [(pose.neck, pose.hip)]
    for limb in (*pose.arms, *pose.legs):
        lines.append((limb.start, limb.joint))
        lines.append((limb.joint, limb.end))
    return tuple(lines)


def distance_to_segment(x: float, y: float, start: Point, end: Point) -> float:
    """点到线段的最短距离（归一化坐标）。"""
    ex, ey = end[0] - start[0], end[1] - start[1]
    length_sq = ex * ex + ey * ey
    if length_sq <= 1e-12:
        return math.hypot(x - start[0], y - start[1])
    t = ((x - start[0]) * ex + (y - start[1]) * ey) / length_sq
    t = min(1.0, max(0.0, t))
    return math.hypot(x - (start[0] + t * ex), y - (start[1] + t * ey))


def hits_pose(pose: StickPose, x: float, y: float, tolerance: float) -> bool:
    """归一化坐标下的线条命中；``tolerance`` 已按单位高度换算。"""
    limit = max(0.0, float(tolerance))
    return any(
        distance_to_segment(x, y, start, end) <= limit for start, end in segments(pose)
    )


@dataclass(slots=True)
class StickAnimator:
    """动作状态机；只吃 dt，不读时钟，方便单测。"""

    state: str = IDLE
    phase: float = 0.0
    timer: float = 0.0
    duration: float = 0.0
    lean: float = 0.0

    def play(self, state: str, seconds: float = 0.0) -> None:
        if state == self.state and state not in TIMED_STATES:
            return
        self.state = state
        self.timer = 0.0
        self.duration = max(0.0, float(seconds)) if state in TIMED_STATES else 0.0
        if state not in TIMED_STATES:
            self.phase = 0.0

    def set_lean(self, radians: float) -> None:
        self.lean = min(max(float(radians), -MAX_LEAN), MAX_LEAN)

    def advance(self, dt: float) -> StickPose:
        step = max(0.0, float(dt))
        self.phase += step
        if self.state in TIMED_STATES and self.duration > 0.0:
            self.timer += step
            if self.timer >= self.duration:
                self.state = IDLE
                self.timer = 0.0
                self.duration = 0.0
        return self.pose()

    def pose(self) -> StickPose:
        if self.state == WAVE:
            progress = 1.0
            if self.duration > 0.0:
                fade_in = 0.12
                fade_out = 0.12
                remaining = self.duration - self.timer
                progress = min(1.0, self.timer / fade_in, remaining / fade_out)
            base = wave_pose(self.phase, progress)
        else:
            builder = POSE_BUILDERS.get(self.state, idle_pose)
            base = builder(self.phase)
        return StickPose(
            neck=base.neck,
            hip=base.hip,
            arms=base.arms,
            legs=base.legs,
            lean=self.lean,
        ).rotated()

    @property
    def busy(self) -> bool:
        return self.state in TIMED_STATES
