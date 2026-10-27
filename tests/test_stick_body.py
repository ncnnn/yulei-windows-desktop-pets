"""火柴人骨架的纯逻辑测试：关节位置、动作状态机与倾斜。"""

from __future__ import annotations

from leiyu_pet.stick_body import (
    ACTION_LABELS,
    CLAP,
    DRAG,
    HEART,
    IDLE,
    MAX_LEAN,
    RANDOM_ACTIONS,
    SALUTE,
    TIMED_STATES,
    WAVE,
    StickAnimator,
    dance_pose,
    distance_to_segment,
    hits_pose,
    idle_pose,
    segments,
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
    for state in (IDLE, *sorted(TIMED_STATES), DRAG):
        animator = StickAnimator()
        if state != IDLE:
            animator.play(state, 3.0)
        for _ in range(10):
            pose = animator.advance(0.1)
            for limb in (*pose.arms, *pose.legs):
                for x, y in (limb.start, limb.joint, limb.end):
                    assert -0.6 <= x <= 0.6
                    assert -0.5 <= y <= 1.2


# ------------------------------------------------------- 2.1.1 新增十款动作


def test_ten_new_actions_are_registered_and_labelled() -> None:
    new_actions = {CLAP, "stretch", "bow", "think", "run", "sleep", "kick", "squat", HEART, SALUTE}
    assert len(new_actions) == 10
    for state in new_actions:
        assert state in TIMED_STATES
        assert state in RANDOM_ACTIONS
        assert ACTION_LABELS[state]
    # 随机池不含交互驱动的状态，否则会出现「没被拖动却在被拎着」
    assert DRAG not in RANDOM_ACTIONS
    assert "spin_360" not in RANDOM_ACTIONS
    assert IDLE not in RANDOM_ACTIONS


def test_every_action_has_a_distinct_silhouette() -> None:
    """十个动作不能长一样：用肘/手/膝/脚的坐标做指纹。"""
    fingerprints = set()
    for state in RANDOM_ACTIONS:
        animator = StickAnimator()
        animator.play(state, 3.0)
        animator.timer = 1.4
        pose = animator.pose()
        key = tuple(
            round(value, 3)
            for limb in (*pose.arms, *pose.legs)
            for point in (limb.joint, limb.end)
            for value in point
        )
        fingerprints.add(key)
    assert len(fingerprints) == len(RANDOM_ACTIONS)


def test_actions_end_and_return_to_idle() -> None:
    for state in RANDOM_ACTIONS:
        animator = StickAnimator()
        animator.play(state, 2.0)
        assert animator.state == state
        animator.advance(2.1)
        assert animator.state == IDLE
        assert animator.busy is False


def test_segments_cover_torso_and_all_limbs() -> None:
    pose = idle_pose(0.0)
    lines = segments(pose)
    # 躯干 + 4 条肢体 × 2 节
    assert len(lines) == 1 + 8


def test_distance_to_segment_clamps_to_endpoints() -> None:
    assert distance_to_segment(0.0, 0.5, (0.0, 0.0), (0.0, 1.0)) == 0.0
    assert distance_to_segment(0.2, 0.5, (0.0, 0.0), (0.0, 1.0)) == 0.2
    # 线段之外按端点算
    assert distance_to_segment(0.3, -0.4, (0.0, 0.0), (0.0, 1.0)) == 0.5


def test_hits_pose_matches_drawn_lines_only() -> None:
    pose = idle_pose(0.0)
    assert hits_pose(pose, 0.0, 0.3, 0.05) is True       # 躯干中段
    assert hits_pose(pose, 0.0, 0.3, 0.001) is True      # 就在线上
    assert hits_pose(pose, 0.0, 0.15, 0.02) is True      # 躯干偏上
    assert hits_pose(pose, 0.25, 0.3, 0.02) is False     # 右侧空白
    assert hits_pose(pose, 0.0, 0.9, 0.02) is False      # 两腿之间
