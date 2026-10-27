from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from leiyu_pet.manifest import load_asset_pack
from leiyu_pet.models import Role
from leiyu_pet.pet_controller import (
    MUTED_LINE,
    MUTED_RELEASE_HINT,
    PetController,
)
from leiyu_pet.proximity import Rect


class FakeWindow:
    def __init__(self, role: Role, rect: Rect):
        self.role = role
        self.rect = rect
        self.visible = True
        self.speaking = False
        self.tilt = 0.0
        self.caption = ""
        self.status = ""
        self.spun = 0
        self.nodded = 0
        self.muted = False

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

    def set_muted(self, value: bool) -> None:
        self.muted = bool(value)

    def set_status_text(self, text: str) -> None:
        self.status = text

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


def build_controller(asset_pack_factory: Callable[..., Path], *, overlap: bool = False):
    pack = load_asset_pack(asset_pack_factory())
    windows = {
        "lei": FakeWindow("lei", Rect(0, 0, 100, 100)),
        "yu": FakeWindow("yu", Rect(120, 0, 100, 100)),
    }
    audio = FakeAudio()
    controller = PetController(pack, windows, audio, start_timer=False)
    # 「叠在一起自动互喷」默认开启；这两只默认就挨着，会自己开聊，
    # 干扰其它用例的播放序列，所以夹具里默认关掉、需要时再打开。
    controller.set_overlap_easter_egg(overlap)
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


def test_overlap_triggers_when_heads_just_touch(asset_pack_factory) -> None:
    """用户理解的「拖到一起」是贴边（间隙 0），旧实现要求面积重叠 55% 才响。"""
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["lei"].rect = Rect(0, 0, 100, 100)
    windows["yu"].rect = Rect(100, 0, 100, 100)  # 紧贴，间隙 0，面积重叠 0
    controller.set_overlap_easter_egg(True)

    controller.update_proximity()

    assert audio.calls and audio.calls[0][0] == "lei"


def test_overlap_ignores_pets_that_are_apart(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["lei"].rect = Rect(0, 0, 100, 100)
    windows["yu"].rect = Rect(400, 0, 100, 100)
    controller.set_overlap_easter_egg(True)

    controller.update_proximity()

    assert audio.calls == []


def test_overlap_gap_threshold_is_configurable(asset_pack_factory) -> None:
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["lei"].rect = Rect(0, 0, 100, 100)
    windows["yu"].rect = Rect(130, 0, 100, 100)  # 间隙 30
    controller.set_overlap_easter_egg(True)
    controller.set_overlap_trigger_gap(0)

    controller.update_proximity()
    assert audio.calls == []

    controller.set_overlap_trigger_gap(40)
    controller.update_proximity()
    assert audio.calls and audio.calls[0][0] == "lei"


def test_overlap_cooldown_is_not_consumed_on_failure(asset_pack_factory) -> None:
    """被隐藏等原因拒绝时不能白烧冷却，否则用户会看到 12 秒死区。"""
    controller, windows, audio = build_controller(asset_pack_factory)
    windows["lei"].rect = Rect(0, 0, 100, 100)
    windows["yu"].rect = Rect(100, 0, 100, 100)
    controller.set_overlap_easter_egg(True)
    windows["yu"].visible = False

    controller.update_proximity()
    assert audio.calls == []
    assert controller._last_overlap_at == 0.0

    windows["yu"].visible = True
    controller.update_proximity()
    assert audio.calls and audio.calls[0][0] == "lei"


def test_battle_rises_volume_and_restores(asset_pack_factory) -> None:
    controller, _windows, audio = build_controller(asset_pack_factory)
    volumes: list[float] = []
    audio.set_volume = volumes.append  # type: ignore[method-assign]
    controller.set_volume(1.0)
    volumes.clear()

    assert controller.start_battle(4) is True
    assert controller.mode == "battle"
    assert volumes == [pytest.approx(0.2)]

    for _ in range(4):
        role, clip_id, _path = audio.calls[-1]
        audio.is_playing = False
        audio.finished.emit(role, clip_id)

    assert volumes == [pytest.approx(v) for v in (0.2, 0.467, 0.733, 1.0)]
    assert controller.mode == "idle"


def test_battle_never_exceeds_user_volume(asset_pack_factory) -> None:
    controller, _windows, audio = build_controller(asset_pack_factory)
    volumes: list[float] = []
    audio.set_volume = volumes.append  # type: ignore[method-assign]
    controller.set_volume(0.3)
    volumes.clear()
    notices: list[str] = []
    controller.notice.connect(notices.append)

    controller.start_battle(4)

    assert volumes == [pytest.approx(0.06)]
    role, clip_id, _path = audio.calls[-1]
    audio.is_playing = False
    audio.finished.emit(role, clip_id)
    assert volumes[-1] == pytest.approx(0.1401, abs=1e-3)
    assert all(value <= 0.3 + 1e-9 for value in volumes)
    # 30% 高于 20% 的起点，无需提示；整段仍然只在用户音量之内。
    assert notices == []


def test_battle_follows_volume_change_mid_playback(asset_pack_factory) -> None:
    """渐强播放中拖音量滑块，应当立刻按当前倍率跟着变。"""
    controller, _windows, audio = build_controller(asset_pack_factory)
    volumes: list[float] = []
    audio.set_volume = volumes.append  # type: ignore[method-assign]
    controller.set_volume(0.5)
    volumes.clear()

    controller.start_battle(4)
    assert volumes == [pytest.approx(0.1)]

    controller.set_volume(0.8)
    assert volumes[-1] == pytest.approx(0.16)


def test_battle_hints_when_volume_below_ladder(asset_pack_factory) -> None:
    controller, _windows, audio = build_controller(asset_pack_factory)
    notices: list[str] = []
    controller.notice.connect(notices.append)
    controller.set_volume(0.1)

    controller.start_battle(4)

    assert notices and "20%" in notices[0]


def test_battle_and_crosstalk_are_mutually_exclusive(asset_pack_factory) -> None:
    controller, _windows, audio = build_controller(asset_pack_factory)
    controller.set_volume(1.0)

    assert controller.start_crosstalk(4) is True
    assert controller.mode == "crosstalk"

    assert controller.start_battle(4) is True
    assert controller.mode == "battle"
    assert controller.crosstalk.position == 1  # 序列已换成决战的新序列


def test_crosstalk_uses_paired_questions_and_answers(asset_pack_factory) -> None:
    """角色交替之外，内容也必须成对：lei 问 1，yu 就答 2。"""
    controller, _windows, audio = build_controller(asset_pack_factory)
    controller.set_crosstalk_lines(4)

    assert controller.start_crosstalk() is True
    assert [call[1] for call in audio.calls] == [1]

    role, clip_id, _path = audio.calls[-1]
    audio.finished.emit(role, clip_id)
    assert [call[1] for call in audio.calls] == [1, 2]
    assert audio.calls[-1][0] == "yu"

    role, clip_id, _path = audio.calls[-1]
    audio.finished.emit(role, clip_id)
    assert [call[1] for call in audio.calls] == [1, 2, 3]


def test_status_badge_is_separate_from_the_dialogue_bubble(asset_pack_factory) -> None:
    """番茄钟倒计时走独立状态条，说话时不会被台词覆盖。"""
    controller, windows, audio = build_controller(asset_pack_factory)

    assert controller.set_status("lei", "番茄钟 · 24:00") is True
    assert windows["lei"].status == "番茄钟 · 24:00"
    assert windows["lei"].caption == ""

    controller.play_solo("lei", 1)

    assert windows["lei"].caption  # 台词在对话气泡里
    assert windows["lei"].status == "番茄钟 · 24:00"  # 倒计时仍然在

    assert controller.clear_status() is True
    assert windows["lei"].status == ""
    assert windows["lei"].caption  # 清状态条不影响台词


def test_overlap_easter_egg_is_on_by_default(asset_pack_factory) -> None:
    """叠在一起自动互喷默认开启，不用每次去设置里打开。"""
    pack = load_asset_pack(asset_pack_factory())
    windows = {
        "lei": FakeWindow("lei", Rect(0, 0, 100, 100)),
        "yu": FakeWindow("yu", Rect(400, 0, 100, 100)),
    }
    controller = PetController(pack, windows, FakeAudio(), start_timer=False)

    assert controller.overlap_enabled is True


def test_muted_click_only_shows_the_banned_line(asset_pack_factory) -> None:
    """捂嘴期间点击不发声、不弹跳，只回一句「已被禁言」。"""
    controller, windows, audio = build_controller(asset_pack_factory)

    controller.set_muted(True)
    controller.handle_click("lei")

    assert audio.calls == []
    assert windows["lei"].caption == MUTED_LINE
    assert windows["lei"].muted is True


def test_muted_blocks_every_dialogue_and_asks_for_release(asset_pack_factory) -> None:
    """捂嘴期间相声/决战/对话都被挡下，并弹出「快把我放出来」。"""
    controller, windows, audio = build_controller(asset_pack_factory)

    controller.set_muted(True)
    assert controller.start_crosstalk(4) is False
    assert controller.start_battle(4) is False
    assert controller.start_pair() is False
    assert controller.play_solo("lei") is None
    assert audio.calls == []
    assert windows["lei"].caption == MUTED_RELEASE_HINT
    assert windows["yu"].caption == MUTED_RELEASE_HINT


def test_muted_blocks_animations_too(asset_pack_factory) -> None:
    """捂嘴期间连转圈都不给：动了不出声更容易被当成坏了。"""
    controller, windows, audio = build_controller(asset_pack_factory)

    controller.set_muted(True)
    controller.handle_double_click("lei")

    assert windows["lei"].spun == 0
    assert windows["lei"].caption == MUTED_RELEASE_HINT


def test_muted_paints_and_clears_the_hand(asset_pack_factory) -> None:
    """捂嘴状态要同步到窗口（窗口负责画那只大手），恢复后撤掉。"""
    controller, windows, _audio = build_controller(asset_pack_factory)

    controller.set_muted(True)
    assert windows["lei"].muted is True
    assert windows["yu"].muted is True

    controller.set_muted(False)
    assert windows["lei"].muted is False
    assert windows["lei"].caption == ""


def test_muted_suppresses_the_overlap_easter_egg(asset_pack_factory) -> None:
    """捂嘴期间被拖到一起也不会互喷，只提示一次求救。"""
    controller, windows, audio = build_controller(asset_pack_factory)
    controller.set_overlap_easter_egg(True)
    windows["yu"].rect = Rect(20, 0, 100, 100)

    controller.set_muted(True)
    controller.update_proximity()

    assert audio.calls == []
    assert windows["lei"].caption == MUTED_RELEASE_HINT
