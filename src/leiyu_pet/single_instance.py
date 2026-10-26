"""QLockFile + QLocalServer 单实例门与唤醒消息。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QByteArray, QCoreApplication, QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    message_received = Signal(str)

    def __init__(self, data_dir: Path, *, identity: str = "LeiYuDesktopPetsWindows") -> None:
        super().__init__()
        self.data_dir = Path(data_dir)
        digest = hashlib.sha256(str(self.data_dir.resolve()).encode("utf-8")).hexdigest()[:12]
        self.server_name = f"{identity}-{digest}"
        self.lock = QLockFile(str(self.data_dir / "instance.lock"))
        self.lock.setStaleLockTime(30_000)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self.acquired = False

    def acquire(self) -> bool:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.lock.tryLock(0):
            self._notify_existing("show")
            self._append_gate_log("拒绝第二实例：已通知现有进程显示桌宠")
            return False
        QLocalServer.removeServer(self.server_name)
        if not self.server.listen(self.server_name):
            self._append_gate_log(f"本地消息服务启动失败：{self.server.errorString()}")
        self.acquired = True
        return True

    def _notify_existing(self, message: str) -> None:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if socket.waitForConnected(500):
            socket.write(QByteArray(message.encode("utf-8")))
            socket.flush()
            socket.waitForBytesWritten(500)
            QCoreApplication.processEvents()
        socket.abort()

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            if not socket.waitForReadyRead(500):
                socket.readyRead.connect(lambda sock=socket: self._read_socket(sock))
            else:
                self._read_socket(socket)

    def _read_socket(self, socket: QLocalSocket) -> None:
        message = bytes(socket.readAll()).decode("utf-8", errors="replace")
        if message:
            self.message_received.emit(message)
        socket.disconnectFromServer()

    def _append_gate_log(self, message: str) -> None:
        try:
            with (self.data_dir / "pet-instance-gate.log").open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        except OSError:
            pass

    def close(self) -> None:
        self.server.close()
        if self.acquired:
            self.lock.unlock()
            self.acquired = False
