"""免打扰时段：纯逻辑，支持跨午夜区间（例如 23:00 → 08:00）。

时间统一用 ``HH:MM`` 字符串保存，避免配置里出现时区/日期等易错结构。
所有函数对非法输入都返回安全值，不抛异常——配置坏掉不应该让桌宠起不来。
"""

from __future__ import annotations

from datetime import datetime

DEFAULT_START = "23:00"
DEFAULT_END = "08:00"


def parse_hhmm(value: str) -> int | None:
    """把 ``"23:05"`` 解析为「当天第几分钟」；非法返回 ``None``。"""
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def normalize_hhmm(value: str, fallback: str) -> str:
    """把任意输入规范成 ``HH:MM``；非法时回退到 ``fallback``。"""
    minutes = parse_hhmm(value)
    if minutes is None:
        minutes = parse_hhmm(fallback)
    if minutes is None:
        minutes = 0
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    """判断 ``now`` 是否落在免打扰区间内。

    起止相同视为「未启用」；跨午夜时按两段区间判断。
    """
    start_minutes = parse_hhmm(start)
    end_minutes = parse_hhmm(end)
    if start_minutes is None or end_minutes is None or start_minutes == end_minutes:
        return False
    current = now.hour * 60 + now.minute
    if start_minutes < end_minutes:
        return start_minutes <= current < end_minutes
    return current >= start_minutes or current < end_minutes
