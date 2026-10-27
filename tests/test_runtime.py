from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, Signal

from leiyu_pet.manifest import load_asset_pack
from leiyu_pet.runtime import PetRuntime


class FakeAudio(QObject):
    started = Signal(str, int)
    position_changed = Signal(str, int, float)
    finished = Signal(str, int)
    stopped = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.volume = 1.0
        self.calls: list[tuple[str, int, Path]] = []

    def set_volume(self, value: float) -> None:
        self.volume = value

    def play(self, role, clip, path) -> None:
        self.calls.append((role, clip.id, path))
        self.started.emit(role, clip.id)

    def stop(self) -> None:
        self.stopped.emit()


def test_runtime_creates_two_windows_and_applies_controls(asset_pack_factory, qtbot) -> None:
    pack = load_asset_pack(asset_pack_factory())
    audio = FakeAudio()
    runtime = PetRuntime(pack, audio=audio, show=False)
    try:
        assert set(runtime.windows) == {"lei", "yu"}
        assert runtime.windows["lei"].pixmap().isNull() is False
        runtime.set_volume(0.4)
        assert audio.volume == 0.4
        runtime.set_pet_size("yu", 290)
        assert runtime.windows["yu"].pet_size == 290
        runtime.set_role_visible("yu", True)
        assert runtime.windows["yu"].isVisible()
        runtime.toggle_role("yu")
        assert not runtime.windows["yu"].isVisible()
    finally:
        runtime.close()


def test_context_menu_routes_random_action_to_controller(asset_pack_factory, qtbot) -> None:
    pack = load_asset_pack(asset_pack_factory())
    audio = FakeAudio()
    runtime = PetRuntime(pack, audio=audio, show=False)
    try:
        menu = runtime.menu_manager.show("lei", QPoint(5, 5))
        random_action = next(action for action in menu.actions() if action.text() == "随机说一段")
        random_action.trigger()
        assert audio.calls[-1][0] == "lei"
        menu.close()
    finally:
        runtime.close()


def test_context_menu_exposes_crosstalk_and_settings(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    opened: list[int] = []
    runtime.on_open_settings = lambda: opened.append(1)
    try:
        menu = runtime.menu_manager.show("yu", QPoint(5, 5))
        texts = [action.text() for action in menu.actions()]
        assert any(text.startswith("相声模式") for text in texts)
        settings_action = next(a for a in menu.actions() if a.text() == "设置…")
        settings_action.trigger()
        assert opened == [1]
        menu.close()
    finally:
        runtime.close()


def test_positions_can_be_captured_and_restored(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        lei = runtime.windows["lei"]
        yu = runtime.windows["yu"]
        lei.move(60, 80)
        yu.move(420, 90)
        captured = runtime.capture_positions()
        # 位置记录的是底边中点：开关躯体时脚不会移动。
        assert captured["lei"] == [60 + lei.width() // 2, 80 + lei.height()]
        assert captured["yu"] == [420 + yu.width() // 2, 90 + yu.height()]

        lei.move(0, 0)
        yu.move(0, 0)
        assert runtime.restore_positions(captured) is True
        assert lei.x() == 60
        assert yu.x() == 420
    finally:
        runtime.close()


def test_restore_positions_rejects_garbage(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        assert runtime.restore_positions(None) is False
        assert runtime.restore_positions({"lei": [], "yu": [1]}) is False
        assert runtime.restore_positions({"lei": ["a", "b"]}) is False
    finally:
        runtime.close()


def test_mute_toggles_and_restores_previous_volume(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    audio = FakeAudio()
    runtime = PetRuntime(pack, audio=audio, show=False)
    try:
        runtime.set_volume(0.4)
        assert runtime.toggle_mute() is True
        assert runtime.muted is True
        assert audio.volume == 0.0
        assert runtime.toggle_mute() is False
        assert runtime.volume == pytest.approx(0.4)
    finally:
        runtime.close()


def test_opacity_and_always_on_top_apply_to_windows(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        runtime.set_opacity(0.5)
        assert runtime.windows["lei"].opacity == pytest.approx(0.5)
        runtime.set_always_on_top(False)
        assert runtime.windows["lei"].always_on_top is False
        assert runtime.windows["yu"].always_on_top is False
    finally:
        runtime.close()


def test_wander_timer_can_be_enabled_and_disabled(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        runtime.set_wander_enabled(True, 30)
        assert runtime._wander_timer.isActive()
        assert runtime._wander_timer.interval() == 30_000
        runtime.set_wander_enabled(False)
        assert not runtime._wander_timer.isActive()
    finally:
        runtime.close()


def test_settings_dialog_builds_against_real_windows(
    asset_pack_factory, qtbot, monkeypatch, tmp_path
) -> None:
    """真窗口的 click_through 是属性，设置页必须按属性读取（回归 v1.2 的 TypeError）。"""
    from leiyu_pet import paths
    from leiyu_pet.config import Config
    from leiyu_pet.settings_dialog import SettingsDialog

    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "config_path", lambda: tmp_path / "config.json")

    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    runtime.config = Config()
    try:
        dialog = SettingsDialog(runtime, runtime.config)
        assert dialog._tabs.count() == 5
        dialog._on_caption_size(15)
        dialog._on_opacity(60)
        assert runtime.windows["lei"].caption_widget.font_size() == 15
        assert runtime.windows["lei"].opacity == pytest.approx(0.6)
        dialog.close()
    finally:
        runtime.close()


def test_stick_action_timer_follows_settings(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        runtime.set_stick_action_settings(True, 20)
        assert runtime._stick_action_timer.isActive()
        assert runtime._stick_action_timer.interval() == 20_000

        runtime.set_stick_action_settings(False, 20)
        assert not runtime._stick_action_timer.isActive()

        # 间隔 0 视为关闭
        runtime.set_stick_action_settings(True, 0)
        assert not runtime._stick_action_timer.isActive()
    finally:
        runtime.close()


def test_stick_body_toggle_reaches_windows(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        runtime.set_stick_body_enabled(False)
        assert all(not window.stick_enabled for window in runtime.windows.values())
        runtime.set_stick_body_enabled(True)
        assert all(window.stick_enabled for window in runtime.windows.values())
    finally:
        runtime.close()


class FakeDuel:
    def __init__(self) -> None:
        self.playing = False
        self.centers = []

    def play_at(self, center) -> bool:
        if self.playing:
            return False
        self.centers.append(center)
        self.playing = True
        return True

    def stop(self) -> None:
        self.playing = False

    def close(self) -> None:
        self.playing = False


def _build_visible_runtime(asset_pack_factory):
    pack = load_asset_pack(asset_pack_factory())
    return PetRuntime(pack, audio=FakeAudio(), show=True)


def test_conversation_start_plays_duel_at_the_midpoint(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        assert runtime.controller.start_pair(1) is True

        assert len(duel.centers) == 1
        lei = runtime.windows["lei"].face_rect_global()
        yu = runtime.windows["yu"].face_rect_global()
        assert duel.centers[0].x() == int((lei.center_x + yu.center_x) / 2)
    finally:
        runtime.close()


def test_solo_playback_does_not_play_duel(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        runtime.controller.play_solo("lei", 1)
        assert duel.centers == []
    finally:
        runtime.close()


def test_duel_is_dropped_when_tilted(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        runtime.windows["lei"].animation.angle = 0.5  # ≈28.6°，超过 5° 门槛
        runtime.controller.start_pair(1)
        assert duel.centers == []
    finally:
        runtime.close()


def test_duel_is_dropped_while_dragging(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        runtime.windows["yu"]._dragging = True
        runtime.controller.start_pair(1)
        assert duel.centers == []
    finally:
        runtime.close()


def test_duel_is_dropped_right_after_a_notice(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        runtime.assistant.notice.emit("番茄钟")
        runtime.controller.start_pair(1)
        assert duel.centers == []
    finally:
        runtime.close()


def test_duel_can_be_switched_off(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    duel = FakeDuel()
    runtime._duel = duel
    try:
        runtime.set_duel_effect_enabled(False)
        runtime.controller.start_pair(1)
        assert duel.centers == []
    finally:
        runtime.close()


def test_auto_dialog_uses_the_configured_mode(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    calls: list[str] = []
    try:
        runtime.controller.start_battle = lambda lines=None: calls.append("battle") or True
        runtime.controller.start_crosstalk = lambda lines=None: calls.append("crosstalk") or True
        runtime.set_auto_dialog(100, "battle")
        runtime._last_auto_dialog_at = 0.0

        runtime._maybe_auto_dialog()

        assert calls == ["battle"]
    finally:
        runtime.close()


def test_auto_dialog_respects_zero_chance_and_cooldown(asset_pack_factory) -> None:
    runtime = _build_visible_runtime(asset_pack_factory)
    calls: list[str] = []
    try:
        runtime.controller.start_battle = lambda lines=None: calls.append("battle") or True
        runtime.controller.start_crosstalk = lambda lines=None: calls.append("crosstalk") or True

        runtime.set_auto_dialog(0, "crosstalk")
        runtime._last_auto_dialog_at = 0.0
        runtime._maybe_auto_dialog()
        assert calls == []

        runtime.set_auto_dialog(100, "crosstalk")
        runtime._last_auto_dialog_at = 0.0
        runtime._maybe_auto_dialog()
        assert calls == ["crosstalk"]

        # 冷却期内不会再来一段
        runtime._maybe_auto_dialog()
        assert calls == ["crosstalk"]
    finally:
        runtime.close()


def test_set_glass_applies_plan_to_both_windows_and_persists(
    asset_pack_factory, monkeypatch, tmp_path
) -> None:
    """面板开关要同时落到两只窗口，并写回配置；关掉后半径仍记住。"""
    from leiyu_pet import paths
    from leiyu_pet import runtime as runtime_module
    from leiyu_pet.config import Config

    monkeypatch.setattr(paths, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(runtime_module, "display_capabilities", lambda: (True, False))

    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    runtime.config = Config()
    try:
        runtime.set_glass(True, 20)
        for window in runtime.windows.values():
            assert window.glass_enabled is True
            assert window.glass_frosted is True
            assert window.glass_radius == 20
        assert runtime.glass_enabled is True
        assert runtime.config.glass_enabled is True
        assert runtime.config.corner_radius == 20

        runtime.set_glass(False, 20)
        for window in runtime.windows.values():
            assert window.glass_enabled is False
        assert runtime.config.glass_enabled is False
        assert runtime.config.corner_radius == 20
    finally:
        runtime.close()


def test_set_glass_degrades_on_a_remote_session(asset_pack_factory, monkeypatch) -> None:
    from leiyu_pet import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "display_capabilities", lambda: (True, True))

    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        runtime.set_glass(True, 14)
        window = runtime.windows["lei"]
        assert window.glass_enabled is True
        assert window.glass_frosted is False
        assert window.glass_radius == 14
        assert window.glass_plan.reason == "remote-session"
    finally:
        runtime.close()


def test_toggle_glass_flips_state(asset_pack_factory, monkeypatch, tmp_path) -> None:
    from leiyu_pet import paths

    monkeypatch.setattr(paths, "config_path", lambda: tmp_path / "config.json")

    pack = load_asset_pack(asset_pack_factory())
    runtime = PetRuntime(pack, audio=FakeAudio(), show=False)
    try:
        assert runtime.toggle_glass() is False
        assert runtime.glass_enabled is False
        assert runtime.toggle_glass() is True
        assert runtime.windows["yu"].glass_enabled is True
    finally:
        runtime.close()
