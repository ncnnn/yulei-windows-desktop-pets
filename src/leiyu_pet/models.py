"""平台无关的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Role = Literal["lei", "yu"]
VoiceMode = Literal["normal", "helium"]


@dataclass(frozen=True, slots=True)
class ClipLine:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class Clip:
    id: int
    role: Role
    text: str
    file: str
    duration: float
    lines: tuple[ClipLine, ...]

    @property
    def timed_lines(self) -> tuple[ClipLine, ...]:
        if self.lines:
            return self.lines
        return (ClipLine(0.0, self.duration, self.text),)

    @property
    def contains_explicit_language(self) -> bool:
        return self.id == 17


@dataclass(frozen=True, slots=True)
class DialoguePair:
    id: int
    lei: int
    yu: int


@dataclass(frozen=True, slots=True)
class PlaybackCommand:
    role: Role
    clip_id: int
    #: 只对这一句生效的音量（0.0-1.0）；``None`` 表示沿用用户设置的总音量。
    #: 决战模式用它做 20%→70% 的逐句爬升。
    volume: float | None = None


@dataclass(frozen=True, slots=True)
class AssetPack:
    root: Path
    normal_clips: tuple[Clip, ...]
    helium_clips: tuple[Clip, ...]
    pairs: tuple[DialoguePair, ...]

    def clips(self, mode: VoiceMode) -> tuple[Clip, ...]:
        return self.helium_clips if mode == "helium" else self.normal_clips

    def clip(self, mode: VoiceMode, clip_id: int) -> Clip:
        try:
            return next(clip for clip in self.clips(mode) if clip.id == clip_id)
        except StopIteration as exc:
            raise KeyError(f"声音模式 {mode} 中不存在片段 {clip_id}") from exc

    def clips_for(
        self,
        role: Role,
        mode: VoiceMode,
        *,
        include_explicit: bool = False,
    ) -> tuple[Clip, ...]:
        return tuple(
            clip
            for clip in self.clips(mode)
            if clip.role == role and (include_explicit or not clip.contains_explicit_language)
        )

    def image_path(self, role: Role) -> Path:
        return self.root / f"{role}.png"

    def audio_path(self, mode: VoiceMode, clip: Clip) -> Path:
        folder = "Clips-helium" if mode == "helium" else "Clips"
        return self.root / folder / clip.file
