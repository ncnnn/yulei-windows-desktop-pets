

def test_jump_keyframe_rises_and_returns() -> None:
    from leiyu_pet.animation import JUMP_HEIGHT, jump_offset

    assert jump_offset(0.0) == 0.0
    assert jump_offset(1.0) == 0.0
    assert jump_offset(0.5) == JUMP_HEIGHT


def test_shake_keyframe_decays_to_zero() -> None:
    from leiyu_pet.animation import shake_offset

    assert shake_offset(0.0) == 0.0
    assert shake_offset(1.0) == 0.0
    assert abs(shake_offset(0.1)) > abs(shake_offset(0.8))


def test_state_jump_and_shake_reach_pose() -> None:
    from leiyu_pet.animation import AnimationState

    state = AnimationState()
    state.jump()
    state.shake()
    pose = state.advance()
    assert pose.offset_y > 0
    assert pose.offset_x > 0

    for _ in range(60):
        state.advance()
    assert state.pose.offset_y == 0
    assert abs(state.pose.offset_x) < 0.001


def test_reduce_motion_suppresses_keyframes() -> None:
    from leiyu_pet.animation import AnimationState

    state = AnimationState(reduce_motion=True)
    state.jump()
    state.shake()
    pose = state.advance()
    assert pose.offset_x == 0
    assert pose.offset_y == 0
