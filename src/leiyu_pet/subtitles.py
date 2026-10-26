"""逐句字幕的确定性时间选择。"""

from __future__ import annotations

from .models import Clip


def caption_at(clip: Clip, seconds: float, *, hold_after: float = 0.4) -> str:
    if seconds < 0 or seconds > clip.duration + hold_after:
        return ""
    selected = clip.timed_lines[0].text
    for line in clip.timed_lines:
        if seconds + 1e-9 < line.start:
            break
        selected = line.text
    return selected
