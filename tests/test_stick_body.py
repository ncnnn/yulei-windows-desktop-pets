"""火柴人骨架的纯逻辑测试：关节位置、动作状态机与倾斜。"""

from __future__ import annotations

from leiyu_pet.stick_body import (
    DANCE,
    DRAG,
    IDLE,
    JUMP,
    MAX_LEAN,
    WAVE,
    StickAnimator,
    dance_pose,
    idle_pose,
    wave_pose,
)


def test_idle_pose_is_symmetric_and_hangs_below_neck() -> None:
    pose = idle_pose(0.0)
    assert pose.neck == (0.0, 0.0)
    assert pose.hip[1] > pose.neck[1]
    left, right = pose.arms
    assert left.start[0] == -right.start[0]
    assert left.end[0] == -right.end[0]


def test_wave_lifts_the_right_hand_above_the_shoulder() -> None:
    pose = wave_pose(0.0, 1.0)
    shoulder, hand = pose.arms[1].start, pose.arms[1].end
    assert hand[1] < shoulder[1]
    assert pose.arms[0].end[1] > pose.arms[0].start[1]  # 另一只手仍自然下垂


def test_dance_moves_both_hands_over_time() -> None:
    first = dance_pose(0.10).arms[1].end[1]
    second = dance_pose(0.35).arms[1].end[1]
    assert first != second


def test_timed_action_returns_to_idle() -> None:
    animator = StickAnimator()
    animator.play(WAVE, 1.0)
    animator.advance(0.5)
    assert animator.state == WAVE
    assert animator.busy is True
    animator.advance(0.6)
    assert animator.state == IDLE
    assert animator.busy is False


def test_drag_and_idle_are_persistent_states() -> None:
    animator = StickAnimator()
    animator.play(DRAG)
    animator.advance(30.0)
    assert animator.state == DRAG
    animator.play(IDLE)
    animator.advance(30.0)
    assert animator.state == IDLE


def test_lean_is_clamped_and_moves_the_feet() -> None:
    animator = StickAnimator()
    animator.set_lean(9.0)
    assert animator.lean == MAX_LEAN
    pose = animator.pose()
    assert abs(pose.legs[0].end[1] - 1.0) > 1e-6


def test_all_states_stay_inside_a_sane_box() -> None:
    for state in (IDLE, WAVE, DANCE, JUMP, DRAG):
        animator = StickAnimator()
        if state != IDLE:
            animator.play(state, 3.0)
        for _ in range(10):
            pose = animator.advance(0.1)
            for limb in (*pose.arms, *pose.legs):
                for x, y in (limb.start, limb.joint, limb.end):
                    assert -0.6 <= x <= 0.6
                    assert -0.5 <= y <= 1.2
