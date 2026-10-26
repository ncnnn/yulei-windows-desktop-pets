"""日志与崩溃兜底测试。"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from leiyu_pet.logging_setup import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    install_excepthook,
    setup_logging,
)


def test_setup_logging_writes_rotating_file(tmp_path) -> None:
    path = tmp_path / "logs" / "pet.log"
    logger = setup_logging(path)
    logger.info("hello")

    for handler in logger.handlers:
        handler.flush()
    assert path.exists()
    assert "hello" in path.read_text(encoding="utf-8")

    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert handlers
    assert handlers[0].maxBytes == LOG_MAX_BYTES
    assert handlers[0].backupCount == LOG_BACKUP_COUNT


def test_setup_logging_is_idempotent(tmp_path) -> None:
    path = tmp_path / "pet.log"
    first = setup_logging(path)
    count = len(first.handlers)
    second = setup_logging(path)
    assert second is first
    assert len(second.handlers) == count


def test_setup_logging_survives_unwritable_path(tmp_path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("x", encoding="utf-8")
    logger = setup_logging(blocked / "pet.log")
    assert logger.name == "leiyu_pet"


def test_excepthook_logs_and_notifies(tmp_path) -> None:
    logger = setup_logging(tmp_path / "pet.log")
    notified = []
    previous = sys.excepthook
    try:
        install_excepthook(logger, notify=lambda title, message: notified.append((title, message)))
        assert sys.excepthook is not previous
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert notified and "RuntimeError" in notified[0][1]
    for handler in logger.handlers:
        handler.flush()
    assert "boom" in (tmp_path / "pet.log").read_text(encoding="utf-8")


def test_excepthook_passes_keyboard_interrupt_through(tmp_path) -> None:
    logger = setup_logging(tmp_path / "pet.log")
    called = []
    previous = sys.excepthook
    try:
        install_excepthook(logger)
        sys.excepthook = lambda *args: called.append(args)
        install_excepthook(logger)
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert called, "KeyboardInterrupt 应交给上一个 hook 处理"
    assert logging.getLogger("leiyu_pet") is logger
