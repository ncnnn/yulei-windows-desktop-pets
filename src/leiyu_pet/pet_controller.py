"""单进程双桌宠的交互编排。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from PySide6.QtCore import QObject, QTimer

from .dialogue import DialogueController
from .models import AssetPack, PlaybackCommand, Role, VoiceMode
from .proximity import ProximityTracker, Rect
from .shuffle import ShuffleBag
from .subtitles import caption_at


class PetWindowPort(Protocol):
    def isVisible(self) -> bool: ...

    def face_rect_global(self) -> Rect: ...

    def set_speaking(self, value: bool) -> None: ...

    def set_tilt(self, angle: float) -> None: ...

    def set_caption(self, text: str) -> None: ...


class PetController(QObject):
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
        self._generation = 0
        self._solo_bags: dict[Role, ShuffleBag[int]] = {}
        self._pair_bag = ShuffleBag(pack.pairs)
        self._rebuild_solo_bags()

        audio.started.connect(self._on_audio_started)
        audio.position_changed.connect(self._on_audio_position)
        audio.finished.connect(self._on_audio_finished)
        audio.stopped.connect(self._on_audio_stopped)

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
        else:
            lei_rect = self.windows["lei"].face_rect_global()
            yu_rect = self.windows["yu"].face_rect_global()
            self.proximity.update(lei_rect, yu_rect)
            angles = self.proximity.tilt_angles(
                lei_rect,
                yu_rect,
                enabled=self.tilt_enabled,
            )
        self.windows["lei"].set_tilt(angles[0])
        self.windows["yu"].set_tilt(angles[1])
        return self.proximity.near

    def handle_click(self, role: Role) -> None:
        if self.update_proximity() and self.both_visible():
            self.start_pair()
        else:
            self.play_solo(role)

    def play_solo(self, role: Role, clip_id: int | None = None) -> None:
        self.dialogue.cancel()
        selected = clip_id if clip_id is not None else self._solo_bags[role].next()
        self._execute(PlaybackCommand(role, selected))

    def start_pair(self, pair_id: int | None = None) -> bool:
        if not self.update_proximity() or not self.both_visible():
            return False
        if pair_id is None:
            pair = self._pair_bag.next()
        else:
            try:
                pair = next(pair for pair in self.pack.pairs if pair.id == pair_id)
            except StopIteration as exc:
                raise KeyError(f"不存在问答组 {pair_id}") from exc
        self._execute(self.dialogue.start(pair))
        return True

    def _execute(self, command: PlaybackCommand) -> None:
        clip = self.pack.clip(self.voice_mode, command.clip_id)
        path = self.pack.audio_path(self.voice_mode, clip)
        self.audio.play(command.role, clip, path)

    def stop_all(self) -> None:
        self._generation += 1
        self.dialogue.cancel()
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

    def set_tilt_enabled(self, enabled: bool) -> None:
        self.tilt_enabled = bool(enabled)
        self.update_proximity()

    def _on_audio_started(self, role: str, clip_id: int) -> None:
        self._generation += 1
        for current_role, window in self.windows.items():
            window.set_speaking(current_role == role)
        clip = self.pack.clip(self.voice_mode, clip_id)
        self.windows[cast(Role, role)].set_caption(caption_at(clip, 0.0))

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
        next_command = self.dialogue.finished(typed_role, clip_id)
        if next_command is not None:
            self._execute(next_command)

    def _on_audio_stopped(self) -> None:
        for window in self.windows.values():
            window.set_speaking(False)
