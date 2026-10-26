"""AudioCoordinator 单元测试：全部使用注入替身，不触碰声卡与真实媒体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from leiyu_pet.audio import AudioCoordinator
from leiyu_pet.models import Clip, Role


@pytest.fixture(scope="module", autouse=True)
def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if existing is not None else QApplication([])


class NamedStatus:
    """模拟 Qt 媒体状态枚举：只有 name 参与结束判定。"""

    def __init__(self, name: str) -> None:
        self.name = name


class FakePlayer(QObject):
    """替代 QMediaPlayer：只记录调用，播放进度由测试手动驱动。"""

    positionChanged = Signal(int)
    mediaStatusChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self.sources: list[QUrl] = []
        self.output: object | None = None
        self.play_calls = 0
        self.stop_calls = 0
        self.position_value = 0
        self.status: NamedStatus = NamedStatus("NoMedia")

    def setAudioOutput(self, output: object) -> None:
        self.output = output

    def setSource(self, url: QUrl) -> None:
        self.sources.append(url)

    def play(self) -> None:
        self.play_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def position(self) -> int:
        return self.position_value

    def mediaStatus(self) -> NamedStatus:
        return self.status

    def emit_position(self, milliseconds: int) -> None:
        self.position_value = milliseconds
        self.positionChanged.emit(milliseconds)

    def emit_status(self, status: object) -> None:
        if isinstance(status, NamedStatus):
            self.status = status
        self.mediaStatusChanged.emit(status)

    def emit_end_of_media(self) -> None:
        self.emit_status(QMediaPlayer.MediaStatus.EndOfMedia)

    def emit_error(self, message: str) -> None:
        self.errorOccurred.emit(QMediaPlayer.Error.ResourceError, message)


class FakeOutput:
    def __init__(self) -> None:
        self.volume = 1.0

    def setVolume(self, value: float) -> None:  # noqa: N802 - 对齐 Qt 命名
        self.volume = value


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def track(self, signal: Any, name: str) -> None:
        signal.connect(lambda *args: self.events.append((name, *args)))

    def names(self) -> list[Any]:
        return [event[0] for event in self.events]


class Bundle:
    def __init__(self) -> None:
        self.player = FakePlayer()
        self.output = FakeOutput()
        self.coordinator = AudioCoordinator(player=self.player, output=self.output)
        self.recorder = Recorder()
        self.recorder.track(self.coordinator.started, "started")
        self.recorder.track(self.coordinator.position_changed, "position_changed")
        self.recorder.track(self.coordinator.finished, "finished")
        self.recorder.track(self.coordinator.stopped, "stopped")
        self.recorder.track(self.coordinator.error, "error")


@pytest.fixture
def bundle() -> Bundle:
    return Bundle()


def clip(clip_id: int, role: Role = "lei") -> Clip:
    return Clip(clip_id, role, f"台词 {clip_id}", f"{role}-{clip_id:02d}.mp3", 1.5, ())


def test_play_sets_source_from_local_file_and_emits_started(bundle: Bundle, tmp_path: Path) -> None:
    path = tmp_path / "雷军 素材" / "lei 01.mp3"
    bundle.coordinator.play("lei", clip(1), path)

    url = bundle.player.sources[0]
    assert isinstance(url, QUrl)
    assert Path(url.toLocalFile()) == path
    assert bundle.player.play_calls == 1
    assert bundle.recorder.events == [("started", "lei", 1)]
    assert bundle.coordinator.current_role == "lei"
    assert bundle.coordinator.current_clip_id == 1
    assert bundle.coordinator.is_playing is True


def test_play_replaces_previous_playback(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator.play("yu", clip(2), tmp_path / "b.mp3")

    assert bundle.player.stop_calls == 1
    assert bundle.player.play_calls == 2
    assert bundle.coordinator.current_role == "yu"
    assert bundle.coordinator.current_clip_id == 2

    bundle.player.emit_end_of_media()
    assert bundle.recorder.names() == ["started", "started", "finished"]
    assert bundle.recorder.events[-1] == ("finished", "yu", 2)


def test_position_changed_converts_milliseconds_to_seconds(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.player.emit_position(1234)

    assert bundle.recorder.events[-1] == ("position_changed", "lei", 1, 1.234)
    assert bundle.coordinator.is_playing is True


def test_non_end_status_does_not_finish(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.player.emit_status(QMediaPlayer.MediaStatus.BufferedMedia)
    bundle.player.emit_status(QMediaPlayer.MediaStatus.LoadedMedia)

    assert "finished" not in bundle.recorder.names()
    assert bundle.coordinator.is_playing is True


def test_end_of_media_emits_finished_once_and_clears_state(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.player.emit_end_of_media()

    assert bundle.recorder.events[-1] == ("finished", "lei", 1)
    assert bundle.coordinator.is_playing is False
    assert bundle.coordinator.current_role is None
    assert bundle.coordinator.current_clip_id is None


def test_stale_callbacks_after_stop_are_ignored(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator.stop()

    assert bundle.recorder.names() == ["started", "stopped"]

    bundle.player.emit_end_of_media()
    bundle.player.emit_position(500)
    bundle.player.emit_error("迟到的错误")

    assert bundle.recorder.names() == ["started", "stopped"]


def test_stale_status_of_old_clip_never_reaches_new_playback(
    bundle: Bundle, tmp_path: Path
) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator.play("yu", clip(2), tmp_path / "b.mp3")

    bundle.player.emit_status(NamedStatus("EndOfMedia"))
    finished_events = [event for event in bundle.recorder.events if event[0] == "finished"]

    assert finished_events == [("finished", "yu", 2)]
    assert len(bundle.player.sources) == 2


def test_error_emits_message_and_clears_state(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.player.emit_error("找不到音频文件")

    assert bundle.recorder.events[-1] == ("error", "找不到音频文件")
    assert bundle.coordinator.is_playing is False
    assert bundle.coordinator.current_role is None


def test_stop_is_idempotent_and_emits_once(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator.stop()
    bundle.coordinator.stop()
    bundle.coordinator.stop()

    assert bundle.recorder.names() == ["started", "stopped"]
    assert bundle.player.stop_calls == 1
    assert bundle.coordinator.is_playing is False
    assert bundle.coordinator.current_role is None


def test_stop_without_playback_is_noop(bundle: Bundle) -> None:
    bundle.coordinator.stop()

    assert bundle.recorder.events == []
    assert bundle.player.stop_calls == 0


def test_stop_then_play_again(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator.stop()
    bundle.coordinator.play("yu", clip(2), tmp_path / "b.mp3")
    bundle.player.emit_end_of_media()

    assert bundle.recorder.names() == ["started", "stopped", "started", "finished"]
    assert bundle.recorder.events[-1] == ("finished", "yu", 2)


def test_volume_is_clamped_to_unit_range(bundle: Bundle) -> None:
    bundle.coordinator.set_volume(0.4)
    assert bundle.output.volume == pytest.approx(0.4)

    bundle.coordinator.set_volume(-3)
    assert bundle.output.volume == 0.0

    bundle.coordinator.set_volume(42)
    assert bundle.output.volume == 1.0


def test_watchdog_reports_failure_when_playback_never_starts(
    bundle: Bundle, tmp_path: Path
) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.coordinator._check_started()

    assert bundle.recorder.events[-1][0] == "error"
    assert "缺少多媒体后端" in bundle.recorder.events[-1][1]
    assert bundle.coordinator.is_playing is False


def test_watchdog_stays_silent_after_position_advances(bundle: Bundle, tmp_path: Path) -> None:
    bundle.coordinator.play("lei", clip(1), tmp_path / "a.mp3")
    bundle.player.position_value = 1200
    bundle.coordinator._check_started()

    assert "error" not in bundle.recorder.names()
    assert bundle.coordinator.is_playing is True


def test_default_player_and_output_are_created() -> None:
    coordinator = AudioCoordinator()

    assert coordinator.is_playing is False
    assert coordinator.current_role is None
    assert coordinator.current_clip_id is None
