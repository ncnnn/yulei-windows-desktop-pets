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
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, int, Path]] = []

    def play(self, role, clip, path) -> None:
        self.calls.append((role, clip.id, path))
        self.started.emit(role, clip.id)

    def stop(self) -> None:
        self.stopped.emit()

    def set_volume(self, volume: float) -> None:
        pass


def build_controller(asset_pack_factory: Callable[..., Path]):
    pack = load_asset_pack(asset_pack_factory())
    windows = {
        "lei": FakeWindow("lei", Rect(0, 0, 100, 100)),
        "yu": FakeWindow("yu", Rect(120, 0, 100, 100)),
    }
    audio = FakeAudio()
    controller = PetController(pack, windows, audio, start_timer=False)
    return controller, windows, audio


def test_click_plays_selected_role_even_when_near(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].rect = Rect(80, 0, 100, 100)  # 与 lei 重叠，near=True
    assert controller.update_proximity() is True

    controller.handle_click("yu")

    assert [call[0] for call in audio.calls] == ["yu"]
    assert windows["yu"].speaking is True
    assert windows["lei"].speaking is False


def test_click_far_only_plays_selected_role(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].rect = Rect(1000, 0, 100, 100)
    controller.handle_click("yu")
    assert [call[0] for call in audio.calls] == ["yu"]


def test_pair_dialogue_still_available_via_menu(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].rect = Rect(80, 0, 100, 100)
    assert controller.start_pair(1) is True
    assert audio.calls[0][0] == "lei"
    role, clip_id, _ = audio.calls[0]
    audio.finished.emit(role, clip_id)
    assert audio.calls[1][0] == "yu"


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


def test_audio_error_clears_speaking_and_reports(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.handle_click("yu")
    assert windows["yu"].speaking is True

    messages: list[str] = []
    controller.playback_error.connect(messages.append)
    audio.error.emit("缺少多媒体后端")

    assert windows["yu"].speaking is False
    assert windows["lei"].speaking is False
    assert windows["yu"].caption == ""
    assert messages == ["缺少多媒体后端"]


def test_crosstalk_alternates_through_all_lines(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_crosstalk_lines(4)

    assert controller.start_crosstalk() is True
    assert [call[0] for call in audio.calls] == ["lei"]

    for _ in range(3):
        role, clip_id, _ = audio.calls[-1]
        audio.finished.emit(role, clip_id)

    assert [call[0] for call in audio.calls] == ["lei", "yu", "lei", "yu"]

    role, clip_id, _ = audio.calls[-1]
    audio.finished.emit(role, clip_id)
    assert len(audio.calls) == 4
    assert controller.crosstalk_active() is False


def test_crosstalk_uses_distinct_pairs_of_clips_per_role(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_crosstalk_lines(6)

    controller.start_crosstalk()
    for _ in range(5):
        role, clip_id, _ = audio.calls[-1]
        audio.finished.emit(role, clip_id)

    lei_ids = [call[1] for call in audio.calls if call[0] == "lei"]
    yu_ids = [call[1] for call in audio.calls if call[0] == "yu"]
    assert len(lei_ids) == 3 and len(yu_ids) == 3
    assert len(set(lei_ids)) == 3
    assert len(set(yu_ids)) == 3


def test_crosstalk_requires_both_pets_visible(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].visible = False

    assert controller.start_crosstalk() is False
    assert audio.calls == []


def test_click_cancels_running_crosstalk(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_crosstalk_lines(6)
    controller.start_crosstalk()

    role, clip_id, _ = audio.calls[-1]
    audio.finished.emit(role, clip_id)
    assert len(audio.calls) == 2

    controller.handle_click("yu")
    assert controller.crosstalk_active() is False

    before = len(audio.calls)
    role, clip_id, _ = audio.calls[-1]
    audio.finished.emit(role, clip_id)
    assert len(audio.calls) == before


def test_stop_all_ends_crosstalk(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.start_crosstalk()

    controller.stop_all()

    assert controller.crosstalk_active() is False
    assert all(window.speaking is False for window in windows.values())
