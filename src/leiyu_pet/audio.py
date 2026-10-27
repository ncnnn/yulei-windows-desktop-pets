"""进程内单例播放器：同一时刻只有一位角色的一个片段发声。

依赖注入 ``player`` / ``output`` 后，单元测试不需要声卡与真实媒体文件。
注入的播放器只需满足 Duck Type 约定：

- 信号 ``positionChanged(ms)``、``mediaStatusChanged(status)``、``errorOccurred(error, message)``；
- 方法 ``setSource(url)``、``play()``、``stop()``。

``status`` 通过 ``name == "EndOfMedia"`` 判定播放结束，因此真实
``QMediaPlayer.MediaStatus`` 与测试替身都能被识别。

``QtMultimedia`` 在真正创建默认播放器/输出时才导入，这样只使用注入替身的
场景（例如单元测试、纯逻辑调用）不会加载多媒体插件。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

from .models import Clip, Role

LOGGER = logging.getLogger(__name__)

_END_OF_MEDIA = "EndOfMedia"
_START_TIMEOUT_MS = 2500
#: 这些状态下后端还没真正出声：如果此时 player 不在 PlayingState，补一次 play()。
#: Qt 的 WMF 后端在 ``stop() → setSource() → play()`` 连发时偶发吞掉 play，
#: 表现为「气泡在走、字幕在动，但没有声音」。
_PENDING_START_STATES = ("LoadedMedia", "BufferedMedia")
_MAX_PLAY_RETRIES = 2
#: 加载偏慢时多给一轮宽限，避免正常但慢的机器被误报成「没有后端」。
_MAX_GRACE = 1


def _create_player() -> Any:
    from PySide6.QtMultimedia import QMediaPlayer

    return QMediaPlayer()


def _create_output() -> Any:
    from PySide6.QtMultimedia import QAudioOutput

    return QAudioOutput()


def output_device_name() -> str:
    """默认播放设备名；拿不到时返回空串（QMediaDevices 延迟导入，避免测试加载插件）。"""
    try:
        from PySide6.QtMultimedia import QMediaDevices

        device = QMediaDevices.defaultAudioOutput()
        return device.description() or ""
    except Exception:  # noqa: BLE001 - 缺少多媒体后端时任何异常都只影响诊断
        return ""


class AudioCoordinator(QObject):
    """串行播放协调器：新片段开始时会先停掉上一位片段。"""

    started = Signal(str, int)
    position_changed = Signal(str, int, float)
    finished = Signal(str, int)
    stopped = Signal()
    error = Signal(str)

    def __init__(
        self,
        player: Any | None = None,
        output: Any | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player: Any = player if player is not None else _create_player()
        self._output: Any = output if output is not None else _create_output()
        attach_output = getattr(self._player, "setAudioOutput", None)
        if callable(attach_output):
            attach_output(self._output)
        self._role: Role | None = None
        self._clip_id: int | None = None
        self._playing = False
        self._grace = 0
        self._retried = False
        self._token = 0
        self._hooks: list[tuple[Any, Any]] = []
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.setInterval(_START_TIMEOUT_MS)
        self._watchdog.timeout.connect(self._check_started)

    @property
    def current_role(self) -> Role | None:
        return self._role

    @property
    def current_clip_id(self) -> int | None:
        return self._clip_id

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self, role: Role, clip: Clip, path: Path | str) -> None:
        self._reset()
        token = self._token
        clip_id = clip.id
        self._grace = _MAX_GRACE
        self._retried = False

        def on_position(milliseconds: int) -> None:
            if token == self._token:
                self.position_changed.emit(role, clip_id, milliseconds / 1000.0)

        def on_status(status: Any) -> None:
            name = getattr(status, "name", "")
            if token != self._token:
                return
            if name == _END_OF_MEDIA:
                self._reset()
                self.finished.emit(role, clip_id)
                return
            if not name or name == "NoMedia":
                return
            # 后端已经真的在播：停掉兜底计时。
            # 这里**不再**在 LoadedMedia/BufferedMedia 时补 play()——那一瞬间
            # playbackState 往往还是 StoppedState，连发 play 会把刚起来的播放
            # 重置，反而造成「有气泡没声音」。补播统一交给 watchdog 判定。
            if self._is_playing() or self._position() > 0:
                self._watchdog.stop()

        def on_error(error: Any, message: str) -> None:
            if token != self._token:
                return
            self._reset()
            self.error.emit(message or str(error))

        self._role = role
        self._clip_id = clip_id
        self._playing = True
        self._hooks = [
            (self._player.positionChanged, on_position),
            (self._player.mediaStatusChanged, on_status),
            (self._player.errorOccurred, on_error),
        ]
        for signal, slot in self._hooks:
            signal.connect(slot)

        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        LOGGER.debug(
            "播放 %s#%s 音量=%.2f 文件=%s", role, clip_id, self.volume, Path(path).name
        )
        self._watchdog.start()
        self.started.emit(role, clip_id)

    def stop(self) -> None:
        if not self._busy():
            return
        self._reset()
        self.stopped.emit()

    def set_volume(self, volume: float) -> None:
        clamped = min(1.0, max(0.0, float(volume)))
        set_volume = getattr(self._output, "setVolume", None)
        if callable(set_volume):
            set_volume(clamped)

    def set_rate(self, rate: float) -> None:
        """播放速率：0.8 慢放 / 1.0 常速 / 1.25 快放，配合氦气模式共三档音色。"""
        clamped = min(2.0, max(0.5, float(rate)))
        set_rate = getattr(self._player, "setPlaybackRate", None)
        if callable(set_rate):
            set_rate(clamped)

    @property
    def volume(self) -> float:
        """当前输出音量（0-1）；读不到时按 0 处理。"""
        get_volume = getattr(self._output, "volume", None)
        if not callable(get_volume):
            return 0.0
        try:
            return float(get_volume())
        except (TypeError, ValueError):
            return 0.0

    def describe(self) -> str:
        """一行音频现状，启动时写进日志——「没声音」时先看这一行。"""
        device = output_device_name() or "（未找到输出设备）"
        return f"输出设备={device}，当前音量={self.volume:.2f}"

    def _reset(self) -> None:
        """断开当前播放的回调、停掉设备并清空状态。"""
        self._watchdog.stop()
        hooks, self._hooks = self._hooks, []
        for signal, slot in hooks:
            signal.disconnect(slot)
        if hooks or self._playing:
            self._player.stop()
        self._role = None
        self._clip_id = None
        self._playing = False
        self._token += 1

    def _is_playing(self) -> bool:
        """当前是否真的在出声（不是「已加载但停着」）。"""
        get_state = getattr(self._player, "playbackState", None)
        if not callable(get_state):
            return False
        try:
            state = get_state()
        except (TypeError, ValueError):
            return False
        return getattr(state, "name", "") == "PlayingState"

    def _position(self) -> int:
        get_position = getattr(self._player, "position", None)
        if not callable(get_position):
            return 0
        try:
            return int(get_position())
        except (TypeError, ValueError):
            return 0

    def _check_started(self) -> None:
        """兜底：迟迟没有进入播放态，说明后端吞了 play 或无法解码。

        补播放在这里而不是状态回调里：``LoadedMedia``/``BufferedMedia`` 到达时
        ``playbackState`` 常常还是 ``StoppedState``，在回调里立刻再 play 会把
        刚起来的播放重置（表现为气泡在走、没有声音）。
        """
        if not self._playing:
            return
        if self._is_playing() or self._position() > 0:
            self._watchdog.stop()
            return
        status = None
        get_status = getattr(self._player, "mediaStatus", None)
        if callable(get_status):
            try:
                status = get_status()
            except (TypeError, ValueError):
                status = None
        name = getattr(status, "name", "")
        if name in _PENDING_START_STATES and not self._retried:
            # 媒体已加载却没起步：补一次 play，把被吞掉的那一句救回来。
            self._retried = True
            self._player.play()
            self._watchdog.start()
            return
        if name in _PENDING_START_STATES and not self._retried:
            # 媒体已加载却没起步：补一次 play，把被吞掉的那一句救回来。
            self._retried = True
            self._player.play()
            self._watchdog.start()
            return
        if name in ("LoadingMedia", *_PENDING_START_STATES) and self._grace > 0:
            # 还在加载：再宽限一轮，别把「机器慢」误判成「没有后端」。
            self._grace -= 1
            self._watchdog.start()
            return
        self._reset()
        self.error.emit("音频未能开始播放：缺少多媒体后端或音频格式不受支持")

    def _busy(self) -> bool:
        return self._playing or bool(self._hooks)
