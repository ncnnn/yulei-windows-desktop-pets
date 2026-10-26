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

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

from .models import Clip, Role

_END_OF_MEDIA = "EndOfMedia"
_START_TIMEOUT_MS = 2000


def _create_player() -> Any:
    from PySide6.QtMultimedia import QMediaPlayer

    return QMediaPlayer()


def _create_output() -> Any:
    from PySide6.QtMultimedia import QAudioOutput

    return QAudioOutput()


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

        def on_position(milliseconds: int) -> None:
            if token == self._token:
                self.position_changed.emit(role, clip_id, milliseconds / 1000.0)

        def on_status(status: Any) -> None:
            name = getattr(status, "name", "")
            if token != self._token:
                return
            if name and name != "NoMedia":
                # 一旦进入加载/缓冲/播放等状态，说明后端已接手，无需再兜底。
                self._watchdog.stop()
            if name != _END_OF_MEDIA:
                return
            self._reset()
            self.finished.emit(role, clip_id)

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

    def _check_started(self) -> None:
        """兜底：若迟迟没有进入加载/播放状态，说明缺少多媒体后端或无法解码。"""
        if not self._playing:
            return
        position = 0
        get_position = getattr(self._player, "position", None)
        if callable(get_position):
            try:
                position = int(get_position())
            except (TypeError, ValueError):
                position = 0
        status = None
        get_status = getattr(self._player, "mediaStatus", None)
        if callable(get_status):
            try:
                status = get_status()
            except (TypeError, ValueError):
                status = None
        name = getattr(status, "name", "")
        if position <= 0 and name in ("", "NoMedia", "LoadingMedia"):
            self._reset()
            self.error.emit("音频未能开始播放：缺少多媒体后端或音频格式不受支持")

    def _busy(self) -> bool:
        return self._playing or bool(self._hooks)
