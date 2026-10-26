from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from leiyu_pet.manifest import load_asset_pack
from leiyu_pet.models import Role
from leiyu_pet.pet_controller import PetController
from leiyu_pet.proximity import Rect


class FakeWindow:
    def __init__(self, role: Role, rect: Rect):
        self.role = role
        self.rect = rect
        self.visible = True
        self.speaking = False
        self.tilt = 0.0
        self.caption = ""

    def isVisible(self) -> bool:
        return self.visible

    def face_rect_global(self) -> Rect:
        return self.rect

    def set_speaking(self, value: bool) -> None:
        self.speaking = value

    def set_tilt(self, angle: float) -> None:
        self.tilt = angle

    def set_caption(self, text: str) -> None:
        self.caption = text


class FakeAudio(QObject):
    started = Signal(str, int)
    position_changed = Signal(str, int, float)
    finished = Signal(str, int)
    stopped = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, int, Path]] = []

    def play(self, role, clip, path) -> None:
        self.calls.append((role, clip.id, path))
        self.started.emit(role, clip.id)

    def stop(self) -> None:
        self.stopped.emit()


def build_controller(asset_pack_factory: Callable[..., Path]):
    pack = load_asset_pack(asset_pack_factory())
    windows = {
        "lei": FakeWindow("lei", Rect(0, 0, 100, 100)),
        "yu": FakeWindow("yu", Rect(120, 0, 100, 100)),
    }
    audio = FakeAudio()
    controller = PetController(pack, windows, audio, start_timer=False)
    return controller, windows, audio


def test_click_near_runs_lei_then_yu(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.handle_click("yu")
    assert audio.calls[0][0] == "lei"
    assert windows["lei"].speaking is True
    role, clip_id, _ = audio.calls[0]
    audio.finished.emit(role, clip_id)
    assert audio.calls[1][0] == "yu"
    assert windows["yu"].speaking is True


def test_click_far_only_plays_selected_role(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].rect = Rect(1000, 0, 100, 100)
    controller.handle_click("yu")
    assert [call[0] for call in audio.calls] == ["yu"]


def test_voice_switch_stops_and_uses_helium(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_voice_mode("helium")
    windows["yu"].rect = Rect(1000, 0, 100, 100)
    controller.play_solo("lei", 1)
    assert "Clips-helium" in str(audio.calls[-1][2])


def test_hidden_peer_disables_pairing_and_tilt(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].visible = False
    controller.handle_click("lei")
    assert [call[0] for call in audio.calls] == ["lei"]
    assert windows["lei"].tilt == 0
