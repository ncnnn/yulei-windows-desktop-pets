"""单进程双桌宠的交互编排。"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from collections.abc import Mapping
from typing import Protocol, cast

from PySide6.QtCore import QObject, QTimer, Signal

from .crosstalk import (
    BATTLE_START_VOLUME,
    DEFAULT_LINES,
    CrosstalkDirector,
    battle_multipliers,
    clamp_lines,
    commands_from_pairs,
    crosstalk_roles,
)
from .dialogue import DialogueController
from .models import AssetPack, PlaybackCommand, Role, VoiceMode
from .proximity import ProximityTracker, Rect, gap, overlap_ratio
from .shuffle import ShuffleBag
from .subtitles import caption_at

#: 重叠彩蛋的判定阈值与冷却时间。
#: 用户理解的「拖到一起」= 两只贴边挨着（间隙 0），所以主判据用像素间隙；
#: 面积重叠率仍然保留，用来兼容「整只叠上去」的玩法。
OVERLAP_TRIGGER_GAP = 24.0
OVERLAP_THRESHOLD = 0.55
OVERLAP_COOLDOWN_SECONDS = 12.0
#: 打开后把每次互喷判定写入日志（默认静默），用于现场排障。
OVERLAP_DEBUG_ENV = "LEIYU_DEBUG_OVERLAP"
HISTORY_LIMIT = 8

Mode = str  # "idle" | "solo" | "pair" | "crosstalk" | "battle"

logger = logging.getLogger(__name__)


class PetWindowPort(Protocol):
    def isVisible(self) -> bool: ...

    def face_rect_global(self) -> Rect: ...

    def set_speaking(self, value: bool) -> None: ...

    def set_tilt(self, angle: float) -> None: ...

    def set_caption(self, text: str) -> None: ...


class PetController(QObject):
    playback_error = Signal(str)
    notice = Signal(str)
    #: 播放模式变化："idle"/"solo"/"pair"/"crosstalk"/"battle"，供托盘更新图标。
    mode_changed = Signal(str)
    #: 一段「对话」开场（pair/crosstalk/battle），供决斗特效使用；独白不触发。
    conversation_started = Signal(str)

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
        #: 用户设置的总音量；决战模式的逐句音量不会超过它。
        self.base_volume = 0.65
        self._volume_overridden = False
        #: 常驻状态气泡（番茄钟倒计时），说话时让位给台词。
        self._status_role: Role | None = None
        self._status_text = ""
        self._generation = 0
        self._solo_bags: dict[Role, ShuffleBag[int]] = {}
        self._pair_bag = ShuffleBag(pack.pairs)
        self._history: dict[Role, deque[tuple[int, str]]] = {
            role: deque(maxlen=HISTORY_LIMIT) for role in ("lei", "yu")
        }
        #: 两只叠在一起时自动来一段问答；默认关闭，由设置页/托盘开启。
        self.overlap_enabled = False
        self.overlap_trigger_gap = OVERLAP_TRIGGER_GAP
        self._overlap_busy = False
        self._last_overlap_at = 0.0
        self._last_overlap_log_at = 0.0
        #: 当前播放模式；决战与相声互斥，切换时先完整退出旧模式。
        self.mode: Mode = "idle"
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
        """两只靠在一起时自动来一段问答（带冷却，避免反复触发）。

        主判据是**脸部包围盒的间隙**：用户把两只拖到贴边（gap≈0）就该触发。
        旧实现只认「面积重叠 ≥55%」，而两只贴边时重叠率只有 0.238，必须把
        一只的头埋进另一只超过一半才会响，实际根本拖不到——这就是「无反应」
        的根因。面积重叠率作为兼容分支保留，覆盖「整只叠上去」的做法。
        """
        if not self.overlap_enabled or lei is None or yu is None:
            return
        current_gap = gap(lei, yu)
        ratio = overlap_ratio(lei, yu)
        close_enough = (
            current_gap <= self.overlap_trigger_gap or ratio >= OVERLAP_THRESHOLD
        )
        if not close_enough:
            self._log_overlap_state(lei, yu, current_gap, ratio, "too-far")
            return
        if self._overlap_busy:
            self._log_overlap_state(lei, yu, current_gap, ratio, "busy")
            return
        if self.crosstalk.running or self.dialogue.active:
            self._log_overlap_state(lei, yu, current_gap, ratio, "already-playing")
            return
        remaining = OVERLAP_COOLDOWN_SECONDS - (time.monotonic() - self._last_overlap_at)
        if remaining > 0:
            self._log_overlap_state(lei, yu, current_gap, ratio, f"cooldown {remaining:.1f}s")
            return

        self._overlap_busy = True
        try:
            started = self.start_pair()
        finally:
            self._overlap_busy = False
        # 只有真的开播才消耗冷却：被隐藏等原因拒绝时不惩罚用户。
        if started:
            self._last_overlap_at = time.monotonic()
        self._log_overlap_state(lei, yu, current_gap, ratio, f"started={started}")

    def _log_overlap_state(
        self,
        lei: Rect,
        yu: Rect,
        current_gap: float,
        ratio: float,
        verdict: str,
    ) -> None:
        """现场排障用的可开关日志：设置 LEIYU_DEBUG_OVERLAP=1 才输出。"""
        if not os.environ.get(OVERLAP_DEBUG_ENV):
            return
        now = time.monotonic()
        if now - self._last_overlap_log_at < 0.5:
            return
        self._last_overlap_log_at = now
        logger.info(
            "overlap lei=(%.0f,%.0f %.0fx%.0f) yu=(%.0f,%.0f %.0fx%.0f) "
            "gap=%.1f(<=%.1f) ratio=%.3f enabled=%s cooldown_left=%.1fs -> %s",
            lei.x,
            lei.y,
            lei.width,
            lei.height,
            yu.x,
            yu.y,
            yu.width,
            yu.height,
            current_gap,
            self.overlap_trigger_gap,
            ratio,
            self.overlap_enabled,
            OVERLAP_COOLDOWN_SECONDS - (now - self._last_overlap_at),
            verdict,
        )

    def set_overlap_easter_egg(self, enabled: bool) -> None:
        self.overlap_enabled = bool(enabled)
        if not self.overlap_enabled:
            self._last_overlap_at = 0.0

    def set_overlap_trigger_gap(self, pixels: float) -> None:
        """两只脸部间隙小于该值即视为「靠在一起」，默认 24px。"""
        self.overlap_trigger_gap = min(max(float(pixels), 0.0), 200.0)

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
        self._enter_mode("solo")
        selected = clip_id if clip_id is not None else self._solo_bags[role].next()
        self._execute(PlaybackCommand(role, selected))

    def _enter_mode(self, mode: Mode) -> None:
        """切换播放模式；决战与相声互斥，先完整退出旧模式。"""
        if self.mode == mode:
            return
        self._leave_mode()
        self.mode = mode
        self.mode_changed.emit(mode)

    def _leave_mode(self) -> None:
        """按「音量 → 气泡 → 模式状态 → 界面通知」的顺序还原。"""
        # 1) 音量还原（决战模式的逐句音量回到用户设置的总音量）
        self._restore_volume()
        # 2) 气泡还原（番茄钟等常驻状态重新显示）
        self._reapply_status()
        # 3) 模式状态清除
        self.dialogue.cancel()
        self.crosstalk.cancel()
        changed = self.mode != "idle"
        self.mode = "idle"
        # 4) 通知界面（托盘图标/提示）
        if changed:
            self.mode_changed.emit("idle")

    def start_crosstalk(
        self,
        lines: int | None = None,
        lead: Role = "lei",
    ) -> bool:
        """相声模式：严格按「一问一答」交替，把多句连续说完。

        关键点：不再给两只各自随机抽词（那样会出现「各说各的」），而是整组
        取用 ``pairs.json`` 的问答对——雷军问哪句，余承东就答对应那句。

        需要两只都可见才有来有回；隐藏了一只时返回 False，由调用方提示。
        """
        if not self.both_visible():
            return False
        total = clamp_lines(self.crosstalk_lines if lines is None else lines)
        commands = self._pair_commands(total)
        if lead == "yu":
            commands = [
                PlaybackCommand(
                    "yu" if command.role == "lei" else "lei",
                    command.clip_id,
                    command.volume,
                )
                for command in commands
            ]
        self.dialogue.cancel()
        self._enter_mode("crosstalk")
        self.conversation_started.emit("crosstalk")
        self._execute(self.crosstalk.start(commands))
        return True

    def start_battle(self, lines: int | None = None) -> bool:
        """决战模式：同样是相声的问答节奏，但每句音量从 20% 递增到 70%。

        音量按「不超过用户当前设置」处理：用户把总音量调到 30%，决战就不会
        突然比平时更吵；静音状态下依然保持静音。
        """
        if not self.both_visible():
            return False
        total = clamp_lines(self.crosstalk_lines if lines is None else lines)
        commands = self._pair_commands(total)
        volumes = battle_multipliers(len(commands))
        staggered = [
            PlaybackCommand(command.role, command.clip_id, volume)
            for command, volume in zip(commands, volumes, strict=True)
        ]
        if self.base_volume < BATTLE_START_VOLUME - 1e-9:
            self.notice.emit(
                f"决战模式需要音量 ≥20% 才能听出 20%→70% 的阶梯，"
                f"当前 {round(self.base_volume * 100)}%，已按当前音量播放"
            )
        self.dialogue.cancel()
        self._enter_mode("battle")
        self.conversation_started.emit("battle")
        self._execute(self.crosstalk.start(staggered))
        return True

    def _pair_commands(self, total: int) -> list[PlaybackCommand]:
        """取问答组生成交替命令；素材缺问答对时退回各自的随机袋。"""
        try:
            return commands_from_pairs(self.pack.pairs, total)
        except ValueError:
            roles = crosstalk_roles(total)
            return [
                PlaybackCommand(role, self._solo_bags[role].next()) for role in roles
            ]

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
        self._enter_mode("pair")
        self.conversation_started.emit("pair")
        self._execute(self.dialogue.start(pair))
        for window in self.windows.values():
            nod = getattr(window, "nod", None)
            if callable(nod):
                nod()
        return True

    def _execute(self, command: PlaybackCommand) -> None:
        clip = self.pack.clip(self.voice_mode, command.clip_id)
        path = self.pack.audio_path(self.voice_mode, clip)
        self._apply_command_volume(command.volume)
        self.audio.play(command.role, clip, path)

    def _apply_command_volume(self, volume: float | None) -> None:
        """应用本句音量；None 表示回到用户设置的总音量。"""
        if volume is None:
            self._restore_volume()
            return
        target = max(0.0, min(float(volume), 1.0))
        if self.base_volume > 0.001:
            target = min(target, self.base_volume)
        else:
            # 静音状态下不因为决战模式突然出声。
            target = 0.0
        self.audio.set_volume(target)
        self._volume_overridden = True

    def _restore_volume(self) -> None:
        if not self._volume_overridden:
            return
        self.audio.set_volume(self.base_volume)
        self._volume_overridden = False

    def set_status(self, role: Role, text: str) -> bool:
        """常驻状态条（番茄钟倒计时等）。

        与对话气泡是两个独立控件，说话时不会互相覆盖——台词走气泡，倒计时
        走底部状态条，可以同时显示。
        """
        message = text.strip()
        if not message:
            return self.clear_status()
        window = self.windows.get(role)
        if window is None or not window.isVisible():
            return False
        self._status_role = role
        self._status_text = message
        setter = getattr(window, "set_status_text", None)
        if callable(setter):
            setter(message)
        return True

    def clear_status(self) -> bool:
        role = self._status_role
        self._status_role = None
        self._status_text = ""
        if role is None:
            return False
        window = self.windows.get(role)
        setter = getattr(window, "set_status_text", None)
        if window is not None and callable(setter):
            setter("")
        return True

    def _reapply_status(self) -> None:
        if self._status_role is None:
            return
        window = self.windows.get(self._status_role)
        setter = getattr(window, "set_status_text", None)
        if window is not None and callable(setter):
            setter(self._status_text)

    def stop_all(self) -> None:
        self._generation += 1
        self._leave_mode()
        self.audio.stop()
        for window in self.windows.values():
            window.set_speaking(False)
            window.set_caption("")
        self._reapply_status()

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
        self.base_volume = min(max(float(volume), 0.0), 1.0)
        if not self._volume_overridden:
            self.audio.set_volume(self.base_volume)

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
                self._reapply_status()

        next_command = self.crosstalk.finished(typed_role, clip_id)
        if next_command is None:
            next_command = self.dialogue.finished(typed_role, clip_id)
        if next_command is not None:
            self._execute(next_command)
            return
        # 整段（含决战模式的音量阶梯）结束：按既定顺序还原。
        self._leave_mode()
        QTimer.singleShot(400, clear_if_still_current)

    def _on_audio_stopped(self) -> None:
        for window in self.windows.values():
            window.set_speaking(False)

    def _on_audio_error(self, message: str) -> None:
        """播放失败时立即清除说话态与字幕，避免停在「一直说话」的样子。"""
        self._leave_mode()
        for window in self.windows.values():
            window.set_speaking(False)
            window.set_caption("")
            shake = getattr(window, "shake", None)
            if callable(shake):
                shake()
        self._reapply_status()
        self.playback_error.emit(message)
