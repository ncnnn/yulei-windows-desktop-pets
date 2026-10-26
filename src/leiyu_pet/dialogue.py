"""雷军先说、余承东后说的进程内问答状态机。"""

from __future__ import annotations

from enum import StrEnum

from .models import DialoguePair, PlaybackCommand, Role


class DialogueStage(StrEnum):
    IDLE = "idle"
    LEI = "lei"
    YU = "yu"
    DONE = "done"
    CANCELLED = "cancelled"


class DialogueController:
    def __init__(self) -> None:
        self.stage = DialogueStage.IDLE
        self.pair: DialoguePair | None = None

    @property
    def active(self) -> bool:
        return self.stage in {DialogueStage.LEI, DialogueStage.YU}

    def start(self, pair: DialoguePair) -> PlaybackCommand:
        self.pair = pair
        self.stage = DialogueStage.LEI
        return PlaybackCommand("lei", pair.lei)

    def finished(self, role: Role, clip_id: int) -> PlaybackCommand | None:
        if self.pair is None:
            return None
        if self.stage == DialogueStage.LEI and role == "lei" and clip_id == self.pair.lei:
            self.stage = DialogueStage.YU
            return PlaybackCommand("yu", self.pair.yu)
        if self.stage == DialogueStage.YU and role == "yu" and clip_id == self.pair.yu:
            self.stage = DialogueStage.DONE
            return None
        return None

    def cancel(self) -> None:
        if self.active:
            self.stage = DialogueStage.CANCELLED
        else:
            self.stage = DialogueStage.IDLE
        self.pair = None

    def reset(self) -> None:
        self.stage = DialogueStage.IDLE
        self.pair = None
