"""半透明面板的样式决策测试（纯逻辑，无需 Qt）。"""

from __future__ import annotations

from leiyu_pet.glass import (
    DEFAULT_RADIUS,
    MAX_RADIUS,
    REASON_DISABLED,
    REASON_NO_COMPOSITING,
    REASON_OK,
    REASON_REMOTE,
    clamp_radius,
    plan_glass,
    radius_for,
)


def test_clamp_radius_keeps_valid_values() -> None:
    assert clamp_radius(0) == 0
    assert clamp_radius(14) == 14
    assert clamp_radius(MAX_RADIUS) == MAX_RADIUS


def test_clamp_radius_bounds_and_fallbacks() -> None:
    assert clamp_radius(999) == MAX_RADIUS
    assert clamp_radius(-3) == 0
    assert clamp_radius("20") == 20
    assert clamp_radius(None) == DEFAULT_RADIUS
    assert clamp_radius("圆一点") == DEFAULT_RADIUS


def test_radius_for_never_exceeds_half_of_short_side() -> None:
    assert radius_for(240, 420, 14) == 14
    assert radius_for(10, 420, 28) == 5
    assert radius_for(0, 420, 28) == 0


def test_disabled_plan_draws_nothing() -> None:
    plan = plan_glass(enabled=False, radius=20)
    assert plan.panel is False
    assert plan.frosted is False
    assert plan.radius == 0
    assert plan.reason == REASON_DISABLED
    assert plan.describe() == "面板已关闭"


def test_enabled_plan_is_frosted_on_a_normal_desktop() -> None:
    plan = plan_glass(enabled=True, radius=20)
    assert plan.panel is True
    assert plan.frosted is True
    assert plan.radius == 20
    assert plan.reason == REASON_OK


def test_compositing_off_drops_frost_but_keeps_radius() -> None:
    """降级顺序里磨砂排在圆角之前：先丢模糊观感，圆角一定留。"""
    plan = plan_glass(enabled=True, radius=18, compositing=False)
    assert plan.panel is True
    assert plan.frosted is False
    assert plan.radius == 18
    assert plan.reason == REASON_NO_COMPOSITING


def test_remote_session_is_checked_before_compositing() -> None:
    plan = plan_glass(enabled=True, radius=8, compositing=False, remote=True)
    assert plan.reason == REASON_REMOTE
    assert plan.frosted is False


def test_plan_radius_is_clamped() -> None:
    assert plan_glass(enabled=True, radius=200).radius == MAX_RADIUS


def test_describe_mentions_frost_and_radius() -> None:
    assert plan_glass(enabled=True, radius=14).describe() == "磨砂面板，圆角 14px"
    degraded = plan_glass(enabled=True, radius=14, remote=True)
    assert "无磨砂" in degraded.describe()
    assert "14px" in degraded.describe()
