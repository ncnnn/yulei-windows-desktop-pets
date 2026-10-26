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
