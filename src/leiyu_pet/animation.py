"""桌宠动画状态：沿用 macOS 原版 30fps 语义的纯函数与小状态类。

这里刻意不依赖 Qt，方便单测直接验证数值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FRAME_SECONDS = 1.0 / 30.0
TILT_EASING = 0.22
SPEAK_PHASE_STEP = 0.50
SPEAK_COMPRESSION = 0.14
SPEAK_BOB_PIXELS = 5.0

MIN_PET_SIZE = 150
MAX_PET_SIZE = 340
DEFAULT_PET_SIZE = 220

#: 点击时的跳跃与抖动关键帧参数（秒 / 像素）。
JUMP_DURATION = 0.50
JUMP_HEIGHT = 20.0
SHAKE_DURATION = 0.36
SHAKE_AMPLITUDE = 7.0
SHAKE_CYCLES = 3.0


def jump_offset(progress: float) -> float:
    """跳跃关键帧：抛物线，0→最高点→0，progress 取 0..1。"""
    p = min(max(progress, 0.0), 1.0)
    return JUMP_HEIGHT * 4.0 * p * (1.0 - p)


def shake_offset(progress: float) -> float:
    """抖动关键帧：衰减正弦，左右晃动后归零。"""
    p = min(max(progress, 0.0), 1.0)
    return SHAKE_AMPLITUDE * math.sin(p * math.pi * 2.0 * SHAKE_CYCLES) * (1.0 - p)


def ease_towards(current: float, target: float, factor: float = TILT_EASING) -> float:
    """指数缓动：每帧向 target 逼近 factor 比例。"""
    return current + (target - current) * factor


def clamp_pet_size(value: float) -> int:
    return max(MIN_PET_SIZE, min(MAX_PET_SIZE, int(value)))


def speaking_pulse(phase: float) -> float:
    """说话脉冲，沿用 macOS 原版 (1-cos(phase))/2，取值 0..1，phase=0 时为 0。"""
    return (1.0 - math.cos(phase)) / 2.0


def compression_for(pulse: float) -> float:
    """纵向压缩系数，说话时压扁至 0.86。"""
    return 1.0 - SPEAK_COMPRESSION * pulse


def bob_for(pulse: float) -> float:
    """向上偏移的像素数，说话时轻微弹跳。"""
    return SPEAK_BOB_PIXELS * pulse


@dataclass(frozen=True, slots=True)
class Pose:
    """一帧的绘制姿态。angle 为弧度，bob 为向上像素偏移。"""

    angle: float = 0.0
    compression: float = 1.0
    bob: float = 0.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    @property
    def angle_degrees(self) -> float:
        return math.degrees(self.angle)


@dataclass(slots=True)
class AnimationState:
    angle: float = 0.0
    target_angle: float = 0.0
    phase: float = 0.0
    speaking: bool = False
    reduce_motion: bool = False
    jump_progress: float = 1.0
    shake_progress: float = 1.0

    @property
    def pulse(self) -> float:
        if self.reduce_motion or not self.speaking:
            return 0.0
        return speaking_pulse(self.phase)

    @property
    def pose(self) -> Pose:
        """当前姿态快照，不推进状态。"""
        if self.reduce_motion:
            return Pose(self.angle, 1.0, 0.0)
        return Pose(
            self.angle,
            compression_for(self.pulse),
            bob_for(self.pulse),
            shake_offset(self.shake_progress),
            jump_offset(self.jump_progress),
        )

    def set_target_angle(self, value: float) -> None:
        self.target_angle = float(value)

    def set_speaking(self, value: bool) -> None:
        self.speaking = bool(value)
        if not self.speaking:
            self.phase = 0.0

    def set_reduce_motion(self, value: bool) -> None:
        self.reduce_motion = bool(value)

    def jump(self) -> None:
        """播放一次跳跃关键帧（点击反馈）。"""
        if not self.reduce_motion:
            self.jump_progress = 0.0

    def shake(self) -> None:
        """播放一次抖动关键帧（被点击/出错时的反馈）。"""
        if not self.reduce_motion:
            self.shake_progress = 0.0

    def advance(self) -> Pose:
        """推进一帧（30fps 语义），返回推进后的姿态。"""
        if self.reduce_motion:
            self.angle = self.target_angle
            self.phase = 0.0
            self.jump_progress = 1.0
            self.shake_progress = 1.0
            return self.pose
        self.angle = ease_towards(self.angle, self.target_angle)
        if self.speaking:
            self.phase += SPEAK_PHASE_STEP
        else:
            self.phase = 0.0
        self.jump_progress = min(1.0, self.jump_progress + FRAME_SECONDS / JUMP_DURATION)
        self.shake_progress = min(1.0, self.shake_progress + FRAME_SECONDS / SHAKE_DURATION)
        return self.pose

    def reset(self) -> None:
        self.angle = 0.0
        self.target_angle = 0.0
        self.phase = 0.0
        self.speaking = False
        self.jump_progress = 1.0
        self.shake_progress = 1.0
