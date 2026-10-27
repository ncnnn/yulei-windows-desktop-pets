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
        self.spun = 0
        self.nodded = 0

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

    def spin(self) -> None:
        self.spun += 1

    def nod(self) -> None:
        self.nodded += 1


class FakeAudio(QObject):
    started = Signal(str, int)
    position_changed = Signal(str, int, float)
    finished = Signal(str, int)
    stopped = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, int, Path]] = []
        self.is_playing = False

    def play(self, role, clip, path) -> None:
        self.calls.append((role, clip.id, path))
        self.is_playing = True
        self.started.emit(role, clip.id)

    def stop(self) -> None:
        self.is_playing = False
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


def test_pair_starts_even_when_far_apart(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].rect = Rect(2000, 0, 100, 100)

    assert controller.start_pair(1) is True
    assert audio.calls[0][0] == "lei"


def test_pair_reports_notice_when_a_pet_is_hidden(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["yu"].visible = False
    notices: list[str] = []
    controller.notice.connect(notices.append)

    assert controller.start_pair(1) is False
    assert notices and "两只" in notices[0]
    assert audio.calls == []


def test_set_rate_is_clamped_and_forwarded(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_rate(5.0)
    assert controller.playback_rate == 2.0
    controller.set_rate(0.1)
    assert controller.playback_rate == 0.5


def test_history_records_played_clips(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.play_solo("lei", 1)
    controller.play_solo("lei", 3)

    assert [clip_id for clip_id, _ in controller.recent("lei")] == [1, 3]
    assert controller.recent("yu") == []
    assert len(controller.recent("lei", 1)) == 1


def test_show_notice_needs_visible_and_idle(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    assert controller.show_notice("lei", "该喝水了") is True
    assert windows["lei"].caption == "该喝水了"

    audio.is_playing = True
    assert controller.show_notice("lei", "正在说话") is False
    audio.is_playing = False

    windows["yu"].visible = False
    assert controller.show_notice("yu", "看不见") is False
    assert controller.show_notice("lei", "   ") is False


def test_double_click_spins_without_stopping_audio(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.play_solo("lei", 1)
    calls_before = len(audio.calls)

    controller.handle_double_click("yu")

    assert windows["yu"].spun == 1
    assert len(audio.calls) == calls_before
    assert audio.is_playing is True


def test_overlap_easter_egg_triggers_pair_with_cooldown(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["lei"].rect = Rect(0, 0, 100, 100)
    windows["yu"].rect = Rect(10, 10, 100, 100)
    controller.set_overlap_easter_egg(True)

    controller.update_proximity()
    assert len(audio.calls) == 1 and audio.calls[0][0] == "lei"

    controller.stop_all()
    controller.update_proximity()
    assert len(audio.calls) == 1  # 冷却期内不重复触发

    controller._last_overlap_at = 0.0
    controller.update_proximity()
    assert len(audio.calls) == 2


def test_pair_dialogue_nods_both_pets(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.start_pair(1)
    assert windows["lei"].nodded == 1
    assert windows["yu"].nodded == 1
