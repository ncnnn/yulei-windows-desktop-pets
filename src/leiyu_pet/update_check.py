"""更新检查：读取 GitHub 最新 Release，比对版本号后提示。

只做「提示」，不自动下载安装——桌宠是常驻进程，静默替换二进制风险太高。
网络失败、被墙、无响应都静默忽略，不影响正常使用。
"""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

RELEASES_API = "https://api.github.com/repos/ncnnn/yulei-windows-desktop-pets/releases/latest"
USER_AGENT = "LeiYuDesktopPets-UpdateCheck"
DEFAULT_TIMEOUT_MS = 8000

_NUMBER_RE = re.compile(r"\d+")


def parse_version(text: str) -> tuple[int, ...]:
    """把 ``v1.1.0`` / ``1.1`` 解析成可比较的元组，非法输入视为 0。"""
    numbers = [int(part) for part in _NUMBER_RE.findall(str(text))[:4]]
    return tuple(numbers) if numbers else (0,)


def is_newer(current: str, latest: str) -> bool:
    """``latest`` 是否比 ``current`` 新（逐段比较，缺位补 0）。"""
    left = parse_version(current)
    right = parse_version(latest)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return right > left


class UpdateChecker(QObject):
    update_available = Signal(str, str)  # 新版本号, 发布页链接
    finished = Signal()
    failed = Signal(str)

    def __init__(self, current_version: str, parent: QObject | None = None,
                 timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.timeout_ms = timeout_ms
        self._manager: QNetworkAccessManager | None = None
        self._reply: QNetworkReply | None = None
        self._timer: QTimer | None = None

    def check(self) -> None:
        """发起一次异步检查；重复调用会先放弃上一次请求。"""
        self._abort()
        manager = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(RELEASES_API))
        request.setRawHeader(b"User-Agent", USER_AGENT.encode())
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = manager.get(request)
        self._manager = manager
        self._reply = reply
        reply.finished.connect(self._on_finished)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(self.timeout_ms)
        timer.timeout.connect(reply.abort)
        timer.start()
        self._timer = timer

    def _abort(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._reply is not None:
            self._reply.finished.disconnect(self._on_finished)
            self._reply.abort()
            self._reply.deleteLater()
            self._reply = None

    def _on_finished(self) -> None:
        reply = self._reply
        self._reply = None
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit(reply.errorString())
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
            tag = str(payload.get("tag_name") or "")
            url = str(payload.get("html_url") or "")
            if tag and is_newer(self.current_version, tag):
                self.update_available.emit(tag, url)
        except (ValueError, OSError) as exc:
            self.failed.emit(str(exc))
        finally:
            reply.deleteLater()
            self.finished.emit()
