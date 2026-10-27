"""磨砂材质的决策测试（纯逻辑，无需 Qt）。

磨砂只服务菜单与设置窗口；桌宠主窗口必须绝对透明，因此这里不涉及主窗口。
"""

from __future__ import annotations

from leiyu_pet.frosted import (
    ACRYLIC_TINT,
    DIALOG_RADIUS,
    MENU_RADIUS,
    REASON_DISABLED,
    REASON_NO_API,
    REASON_NO_COMPOSITING,
    REASON_OK,
    REASON_REMOTE,
    clamp_radius,
    plan_frosted,
)


def test_clamp_radius_keeps_valid_values() -> None:
    assert clamp_radius(0) == 0
    assert clamp_radius(MENU_RADIUS) == MENU_RADIUS
    assert clamp_radius(999) == 24


def test_clamp_radius_falls_back_on_garbage() -> None:
    assert clamp_radius(None) == DIALOG_RADIUS
    assert clamp_radius("圆一点") == DIALOG_RADIUS
    assert clamp_radius("12") == 12


def test_disabled_plan_has_no_material() -> None:
    plan = plan_frosted(enabled=False)
    assert plan.enabled is False
    assert plan.acrylic is False
    assert plan.radius == 0
    assert plan.reason == REASON_DISABLED
    assert plan.describe() == "磨砂已关闭"


def test_enabled_plan_prefers_system_acrylic() -> None:
    plan = plan_frosted(enabled=True, radius=DIALOG_RADIUS)
    assert plan.enabled is True
    assert plan.acrylic is True
    assert plan.radius == DIALOG_RADIUS
    assert plan.reason == REASON_OK
    assert "系统磨砂" in plan.describe()


def test_missing_api_falls_back_to_painted_background() -> None:
    plan = plan_frosted(enabled=True, acrylic_available=False)
    assert plan.enabled is True
    assert plan.acrylic is False
    assert plan.reason == REASON_NO_API
    assert "无系统模糊" in plan.describe()


def test_remote_session_and_compositing_degrade_too() -> None:
    assert plan_frosted(enabled=True, remote=True).reason == REASON_REMOTE
    assert plan_frosted(enabled=True, compositing=False).reason == REASON_NO_COMPOSITING
    for plan in (
        plan_frosted(enabled=True, remote=True),
        plan_frosted(enabled=True, compositing=False),
    ):
        assert plan.enabled is True
        assert plan.acrylic is False


def test_acrylic_tint_is_translucent_not_opaque() -> None:
    assert ACRYLIC_TINT[3] < 255
