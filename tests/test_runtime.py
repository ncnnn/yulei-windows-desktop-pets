from __future__ import annotations

from pathlib import Path

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
        runtime.windows["lei"].move(60, 80)
        runtime.windows["yu"].move(420, 90)
        captured = runtime.capture_positions()
        assert captured["lei"] == [60, 80]
        assert captured["yu"] == [420, 90]

        runtime.windows["lei"].move(0, 0)
        runtime.windows["yu"].move(0, 0)
        assert runtime.restore_positions(captured) is True
        assert runtime.windows["lei"].x() == 60
        assert runtime.windows["yu"].x() == 420
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
