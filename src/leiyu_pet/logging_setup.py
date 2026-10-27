"""日志与崩溃兜底：滚动日志文件 + 未捕获异常落盘。

桌宠是常驻进程，日志不能无限增长，所以用 ``RotatingFileHandler``
（512 KB × 3 份）。未捕获异常在写盘之外还会通过 ``notify`` 回调提示用户，
避免「默默消失」。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME

LOGGER_NAME = "leiyu_pet"
LOG_MAX_BYTES = 512 * 1024
LOG_BACKUP_COUNT = 2
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(path: Path, *, level: int = logging.INFO) -> logging.Logger:
    """给包级 logger 挂上滚动文件处理器（重复调用不会叠加）。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    path = Path(path)
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == path.resolve():
                return logger
            logger.removeHandler(handler)
            handler.close()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return logger
    try:
        handler = RotatingFileHandler(
            path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return logger
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logger


def install_excepthook(
    logger: logging.Logger,
    notify: Callable[[str, str], None] | None = None,
) -> None:
    """接管 ``sys.excepthook``：异常写日志，可选弹出托盘提示。"""
    previous = sys.excepthook

    def hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc_value, exc_tb)
            return
        logger.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
        if notify is not None:
            try:
                notify(APP_NAME, f"出现异常：{exc_type.__name__}，详情见日志")
            except Exception:
                pass

    sys.excepthook = hook
