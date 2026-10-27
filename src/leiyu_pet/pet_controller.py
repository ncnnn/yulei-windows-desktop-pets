"""单进程双桌宠的交互编排。"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Mapping
from typing import Protocol, cast

from PySide6.QtCore import QObject, QTimer, Signal

from .crosstalk import DEFAULT_LINES, CrosstalkDirector, clamp_lines, crosstalk_roles
from .dialogue import DialogueController
from .models import AssetPack, PlaybackCommand, Role, VoiceMode
from .proximity import ProximityTracker, Rect, overlap_ratio
from .shuffle import ShuffleBag
from .subtitles import caption_at

#: 重叠彩蛋的触发阈值与冷却时间。
OVERLAP_THRESHOLD = 0.55
OVERLAP_COOLDOWN_SECONDS = 30.0
HISTORY_LIMIT = 8


class PetWindowPort(Protocol):
    def isVisible(self) -> bool: ...

    def face_rect_global(self) -> Rect: ...

    def set_speaking(self, value: bool) -> None: ...

    def set_tilt(self, angle: float) -> None: ...

    def set_caption(self, text: str) -> None: ...


class PetController(QObject):
    playback_error = Signal(str)
    notice = Signal(str)

    def __init__(
        self,
        pack: AssetPack,
        windows: Mapping[Role, PetWindowPort],
        audio: QObject,
        *,
        parent: QObject | None = None,
        start_timer: bool = True,
    ) -> None:
        super().__init__(parent)
        self.pack = pack
        self.windows = dict(windows)
        self.audio = audio
        self.voice_mode: VoiceMode = "normal"
        self.include_explicit = False
        self.tilt_enabled = True
        self.proximity = ProximityTracker()
        self.dialogue = DialogueController()
        self.crosstalk = CrosstalkDirector()
        self.crosstalk_lines = DEFAULT_LINES
        self.playback_rate = 1.0
        self._generation = 0
        self._solo_bags: dict[Role, ShuffleBag[int]] = {}
        self._pair_bag = ShuffleBag(pack.pairs)
        self._history: dict[Role, deque[tuple[int, str]]] = {
            role: deque(maxlen=HISTORY_LIMIT) for role in ("lei", "yu")
        }
        #: 两只叠在一起时自动来一段问答；默认关闭，由设置页/托盘开启。
        self.overlap_enabled = False
        self._overlap_busy = False
        self._last_overlap_at = 0.0
        self._rebuild_solo_bags()

        audio.started.connect(self._on_audio_started)
        audio.position_changed.connect(self._on_audio_position)
        audio.finished.connect(self._on_audio_finished)
        audio.stopped.connect(self._on_audio_stopped)
        audio.error.connect(self._on_audio_error)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_proximity)
        if start_timer:
            self.timer.start()

    def _rebuild_solo_bags(self) -> None:
        self._solo_bags = {
            role: ShuffleBag(
                clip.id
                for clip in self.pack.clips_for(
                    role,
                    self.voice_mode,
                    include_explicit=self.include_explicit,
                )
            )
            for role in cast(tuple[Role, Role], ("lei", "yu"))
        }

    def both_visible(self) -> bool:
        return all(window.isVisible() for window in self.windows.values())

    def update_proximity(self) -> bool:
        if not self.both_visible():
            self.proximity.near = False
            angles = (0.0, 0.0)
            self._maybe_overlap_easter_egg(None, None)
        else:
            lei_rect = self.windows["lei"].face_rect_global()
            yu_rect = self.windows["yu"].face_rect_global()
            self.proximity.update(lei_rect, yu_rect)
            angles = self.proximity.tilt_angles(
                lei_rect,
                yu_rect,
                enabled=self.tilt_enabled,
            )
            self._maybe_overlap_easter_egg(lei_rect, yu_rect)
        self.windows["lei"].set_tilt(angles[0])
        self.windows["yu"].set_tilt(angles[1])
        return self.proximity.near

    def _maybe_overlap_easter_egg(self, lei: Rect | None, yu: Rect | None) -> None:
        """两只叠在一起时自动来一段问答，带冷却，避免反复触发。"""
        if not self.overlap_enabled or lei is None or yu is None:
            return
        if self._overlap_busy or self.crosstalk.running or self.dialogue.active:
            return
        if overlap_ratio(lei, yu) < OVERLAP_THRESHOLD:
            return
        if time.monotonic() - self._last_overlap_at < OVERLAP_COOLDOWN_SECONDS:
            return
        self._overlap_busy = True
        self._last_overlap_at = time.monotonic()
        try:
            self.start_pair()
        finally:
            self._overlap_busy = False

    def set_overlap_easter_egg(self, enabled: bool) -> None:
        self.overlap_enabled = bool(enabled)
        if not self.overlap_enabled:
            self._last_overlap_at = 0.0

    def _audio_is_playing(self) -> bool:
        return bool(getattr(self.audio, "is_playing", False))

    def show_notice(self, role: Role, text: str, *, seconds: float = 6.0) -> bool:
        """只弹字幕气泡、不发声（提醒类功能用）。

        正在播放音频时返回 ``False``：此时字幕由音频进度驱动，硬插进去会被
        下一帧覆盖。调用方可以退回托盘气泡。
        """
        window = self.windows.get(role)
        if window is None or not window.isVisible() or not text.strip():
            return False
        if self._audio_is_playing():
            return False
        message = text.strip()
        window.set_caption(message)

        def clear_if_unchanged() -> None:
            getter = getattr(window, "caption", None)
            current = getter() if callable(getter) else getattr(window, "caption", "")
            if current == message:
                window.set_caption("")

        QTimer.singleShot(max(1, int(seconds * 1000)), clear_if_unchanged)
        return True

    def handle_double_click(self, role: Role) -> None:
        """双击彩蛋：原地转一圈（不打断正在说的话）。"""
        spin = getattr(self.windows[role], "spin", None)
        if callable(spin):
            spin()

    def recent(self, role: Role, limit: int = HISTORY_LIMIT) -> list[tuple[int, str]]:
        """最近播放过的片段（新的在后），供「最近说过」菜单重播。"""
        return list(self._history[role])[-max(1, int(limit)):]

    def is_busy(self) -> bool:
        """当前是否有任何发声/对话在进行。"""
        return self._audio_is_playing() or self.dialogue.active or self.crosstalk.running

    def handle_click(self, role: Role) -> None:
        """点击某只桌宠只播放它自己的独白。

        两人对话由右键/托盘菜单的「两人对话一句」显式触发；这里若按靠近与否
        改播对话，会出现「点余承东却由雷军先开口」的错位。
        """
        self.update_proximity()
        jump = getattr(self.windows[role], "jump", None)
        if callable(jump):
            jump()
        self.play_solo(role)

    def play_solo(self, role: Role, clip_id: int | None = None) -> None:
        self.dialogue.cancel()
        self.crosstalk.cancel()
        selected = clip_id if clip_id is not None else self._solo_bags[role].next()
        self._execute(PlaybackCommand(role, selected))

    def start_crosstalk(
        self,
        lines: int | None = None,
        lead: Role = "lei",
    ) -> bool:
        """相声模式：两只交替把多句连续说完，本质是「连续一句」串起来。

        需要两只都可见才有来有回；隐藏了一只时返回 False，由调用方提示。
        """
        if not self.both_visible():
            return False
        total = self.crosstalk_lines if lines is None else lines
        roles = crosstalk_roles(clamp_lines(total), lead)
        commands = [PlaybackCommand(role, self._solo_bags[role].next()) for role in roles]
        self.dialogue.cancel()
        self._execute(self.crosstalk.start(commands))
        return True

    def crosstalk_active(self) -> bool:
        return self.crosstalk.running

    def set_crosstalk_lines(self, lines: int) -> None:
        self.crosstalk_lines = clamp_lines(lines)

    def start_pair(self, pair_id: int | None = None) -> bool:
        """两人对话一句。

        不再要求两只必须靠在一起：距离只影响歪头，不影响能不能聊。离得远时
        用户点了菜单也照样播，避免「点了没反应」的错觉；只有隐藏了其中一只
        才拒绝，并明确告知原因。
        """
        self.update_proximity()
        if not self.both_visible():
            self.notice.emit("需要两只桌宠都在场才能对话，已为你显示全部")
            return False
        if pair_id is None:
            pair = self._pair_bag.next()
        else:
            try:
                pair = next(pair for pair in self.pack.pairs if pair.id == pair_id)
            except StopIteration as exc:
                raise KeyError(f"不存在问答组 {pair_id}") from exc
        self.crosstalk.cancel()
        self._execute(self.dialogue.start(pair))
        for window in self.windows.values():
            nod = getattr(window, "nod", None)
            if callable(nod):
                nod()
        return True

    def _execute(self, command: PlaybackCommand) -> None:
        clip = self.pack.clip(self.voice_mode, command.clip_id)
        path = self.pack.audio_path(self.voice_mode, clip)
        self.audio.play(command.role, clip, path)

    def stop_all(self) -> None:
        self._generation += 1
        self.dialogue.cancel()
        self.crosstalk.cancel()
        self.audio.stop()
        for window in self.windows.values():
            window.set_speaking(False)
            window.set_caption("")

    def set_voice_mode(self, mode: VoiceMode) -> None:
        if mode not in ("normal", "helium"):
            raise ValueError(f"未知声音模式：{mode}")
        if mode == self.voice_mode:
            return
        self.stop_all()
        self.voice_mode = mode
        self._rebuild_solo_bags()

    def set_include_explicit(self, enabled: bool) -> None:
        self.include_explicit = bool(enabled)
        self._rebuild_solo_bags()

    def set_distance(self, distance: float) -> None:
        self.proximity.distance = min(max(float(distance), 0.0), 100.0)
        self.update_proximity()

    def set_volume(self, volume: float) -> None:
        self.audio.set_volume(min(max(float(volume), 0.0), 1.0))

    def set_rate(self, rate: float) -> None:
        self.playback_rate = min(max(float(rate), 0.5), 2.0)
        set_rate = getattr(self.audio, "set_rate", None)
        if callable(set_rate):
            set_rate(self.playback_rate)

    def set_tilt_enabled(self, enabled: bool) -> None:
        self.tilt_enabled = bool(enabled)
        self.update_proximity()

    def _on_audio_started(self, role: str, clip_id: int) -> None:
        self._generation += 1
        for current_role, window in self.windows.items():
            window.set_speaking(current_role == role)
        clip = self.pack.clip(self.voice_mode, clip_id)
        typed_role = cast(Role, role)
        self._history[typed_role].append((clip_id, clip.text))
        self.windows[typed_role].set_caption(caption_at(clip, 0.0))

    def _on_audio_position(self, role: str, clip_id: int, seconds: float) -> None:
        clip = self.pack.clip(self.voice_mode, clip_id)
        self.windows[cast(Role, role)].set_caption(caption_at(clip, seconds))

    def _on_audio_finished(self, role: str, clip_id: int) -> None:
        typed_role = cast(Role, role)
        self.windows[typed_role].set_speaking(False)
        generation = self._generation

        def clear_if_still_current() -> None:
            if generation == self._generation:
                self.windows[typed_role].set_caption("")

        QTimer.singleShot(400, clear_if_still_current)
        next_command = self.crosstalk.finished(typed_role, clip_id)
        if next_command is None:
            next_command = self.dialogue.finished(typed_role, clip_id)
        if next_command is not None:
            self._execute(next_command)

    def _on_audio_stopped(self) -> None:
        for window in self.windows.values():
            window.set_speaking(False)

    def _on_audio_error(self, message: str) -> None:
        """播放失败时立即清除说话态与字幕，避免停在「一直说话」的样子。"""
        self.dialogue.cancel()
        self.crosstalk.cancel()
        for window in self.windows.values():
            window.set_speaking(False)
            window.set_caption("")
            shake = getattr(window, "shake", None)
            if callable(shake):
                shake()
        self.playback_error.emit(message)
