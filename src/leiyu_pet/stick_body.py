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
#: 预留但暂未实现的状态名，供后续扩展（不改结构即可加）。
RESERVED = ("happy", "fall")

TIMED_STATES = frozenset({WAVE, DANCE, JUMP})

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
    legs = tuple(
        Limb(
            (side * HIP_X, HIP_Y),
            (side * (HIP_X + 0.03), KNEE_Y),
            (side * (HIP_X + 0.05), FOOT_Y),
        )
        for side in (-1.0, 1.0)
    )
    return StickPose(neck=(0.0, 0.0), hip=hip, arms=arms, legs=legs)  # type: ignore[arg-type]


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
        elif self.state == DANCE:
            base = dance_pose(self.phase)
        elif self.state == JUMP:
            base = jump_pose(self.phase)
        elif self.state == DRAG:
            base = drag_pose(self.phase)
        else:
            base = idle_pose(self.phase)
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
