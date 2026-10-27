"""相声模式：两只桌宠按 1-2-1-2 的节奏交替，把多句连续说完。

这里只做纯逻辑（不导入 PySide6）：给定总句数决定角色序列，并按播放完成
事件逐句推进。真正的播放由 ``PetController`` 执行。
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .models import DialoguePair, PlaybackCommand, Role

MIN_LINES = 2
MAX_LINES = 20
DEFAULT_LINES = 20
#: 菜单里提供的快捷句数，避免用户面对一个无意义的自由输入框。
LINE_PRESETS = (8, 12, 20)

#: 副歌判定阈值（秒）：一组问答里较长的那句都短于它，就当它是「短句副歌」。
#: 素材里「总有机会 / 追不上」只有 0.3-1.0 秒，靠这个把它们和正经问答分开。
CHORUS_MAX_SECONDS = 1.5


def clamp_lines(lines: int) -> int:
    """把句数夹到合理区间，非法输入回退默认值。"""
    try:
        value = int(lines)
    except (TypeError, ValueError):
        return DEFAULT_LINES
    return min(max(value, MIN_LINES), MAX_LINES)


def crosstalk_roles(lines: int = DEFAULT_LINES, lead: Role = "lei") -> list[Role]:
    """返回交替的角色序列，例如 ``lines=4, lead="lei"`` → lei, yu, lei, yu。"""
    total = clamp_lines(lines)
    other: Role = "yu" if lead == "lei" else "lei"
    return [lead if index % 2 == 0 else other for index in range(total)]


def commands_from_pairs(
    pairs: Sequence[DialoguePair],
    lines: int = DEFAULT_LINES,
    *,
    rng: random.Random | None = None,
) -> list[PlaybackCommand]:
    """按「一问一答」生成严格交替的命令序列。

    与旧实现的关键区别：这里不再给每只角色各抽一句，而是整组取用
    ``pairs.json`` 里的问答对——雷军问哪句，余承东就答对应的那句。

    顺序规则：第一轮按素材里的原始顺序走完，**用完之后整轮打乱再循环**，
    而不是每句各自随机重选（那样会出现答非所问）。
    """
    total = clamp_lines(lines)
    if not pairs:
        raise ValueError("素材包没有可用的问答组")
    source = list(pairs)
    commands: list[PlaybackCommand] = []
    order = list(source)
    index = 0
    last: DialoguePair | None = None
    while len(commands) < total:
        if index >= len(order):
            # 上一轮走完：整轮重排，保持每组问答仍是成对出现的。
            order = list(source)
            if len(order) > 1:
                (rng or random).shuffle(order)
                # 新一轮别接着上一轮最后一组，否则会听到「同一句连着两遍」。
                if order[0] is last:
                    order[0], order[1] = order[1], order[0]
            index = 0
        pair = order[index]
        index += 1
        last = pair
        commands.append(PlaybackCommand("lei", pair.lei))
        if len(commands) < total:
            commands.append(PlaybackCommand("yu", pair.yu))
    return commands


def crosstalk_script(
    pack: Any,
    lines: int = DEFAULT_LINES,
) -> list[PlaybackCommand]:
    """整段的剧本：正剧问答 → 短句副歌来回 → 固定收尾。

    素材本身就是一个完整段子，顺序是有讲究的：前几组是正经问答，中段是
    「总有机会 / 追不上」的短促来回，最后一句是没被任何问答组引用的收尾梗。
    随机取组会把收尾句插在中间、把副歌放在开头，段子就散了——所以这里按
    结构排布，句数不够就用副歌补齐，够长就正好停在收尾句上。

    仍然保证严格的「雷军说一句、余承东答一句」交替。
    """
    total = clamp_lines(lines)
    pairs = list(getattr(pack, "pairs", ()))
    if not pairs:
        raise ValueError("素材包没有可用的问答组")
    clips: dict[int, Any] = {clip.id: clip for clip in getattr(pack, "normal_clips", ())}

    def longest(pair: DialoguePair) -> float:
        lei = clips.get(pair.lei)
        yu = clips.get(pair.yu)
        if lei is None or yu is None:
            return CHORUS_MAX_SECONDS
        return max(float(getattr(lei, "duration", 0.0)), float(getattr(yu, "duration", 0.0)))

    chorus = [pair for pair in pairs if longest(pair) < CHORUS_MAX_SECONDS]
    main = [pair for pair in pairs if longest(pair) >= CHORUS_MAX_SECONDS]
    if not main:
        main, chorus = pairs, []
    used = {pair.lei for pair in pairs} | {pair.yu for pair in pairs}
    # 收尾句：没被任何问答组引用的最后一句（素材里就是那句收尾梗）。
    orphans = [clip_id for clip_id in sorted(clips) if clip_id not in used]
    finale = orphans[-1] if orphans else None

    script: list[PlaybackCommand] = []
    for pair in main:
        script.append(PlaybackCommand("lei", pair.lei))
        script.append(PlaybackCommand("yu", pair.yu))
        if len(script) >= total:
            return script[:total]

    if finale is None:
        # 没有收尾句就用副歌把剩下的填满。
        _fill_chorus(script, chorus, total, fallback=main)
        return script[:total]

    room = total - len(script) - 1
    if room > 0:
        _fill_chorus(script, chorus, len(script) + room, fallback=main)
    if len(script) < total:
        script.append(PlaybackCommand(clips[finale].role, finale))
    return script[:total]


def _fill_chorus(
    script: list[PlaybackCommand],
    chorus: list[DialoguePair],
    upto: int,
    *,
    fallback: list[DialoguePair] = (),  # noqa: B006 - 只读，不需要默认值工厂
) -> None:
    """用短句副歌成对地把剧本填到 ``upto`` 句。

    素材没有副歌（或副歌不够）时退回正剧问答循环，保证剧本凑得满句数。
    """
    source = chorus or fallback
    if not source:
        return
    index = 0
    while len(script) < upto:
        pair = source[index % len(source)]
        index += 1
        script.append(PlaybackCommand("lei", pair.lei))
        if len(script) < upto:
            script.append(PlaybackCommand("yu", pair.yu))


@dataclass(slots=True)
class CrosstalkDirector:
    """按顺序派发多句台词；每句播完才推到下一句。"""

    commands: list[PlaybackCommand] = field(default_factory=list)
    index: int = 0
    running: bool = False

    def start(self, commands: list[PlaybackCommand]) -> PlaybackCommand:
        if not commands:
            raise ValueError("相声模式至少需要一句台词")
        self.commands = list(commands)
        self.index = 0
        self.running = True
        return self.commands[0]

    def finished(self, role: str, clip_id: int) -> PlaybackCommand | None:
        """当前这句播完后返回下一句；序列结束或事件不匹配时返回 None。"""
        if not self.running or self.index >= len(self.commands):
            return None
        current = self.commands[self.index]
        if current.role != role or current.clip_id != clip_id:
            return None
        self.index += 1
        if self.index >= len(self.commands):
            self.cancel()
            return None
        return self.commands[self.index]

    def cancel(self) -> None:
        self.commands = []
        self.index = 0
        self.running = False

    @property
    def remaining(self) -> int:
        if not self.running:
            return 0
        return max(len(self.commands) - self.index, 0)

    @property
    def position(self) -> int:
        """当前是第几句（1 起算），未运行时为 0。"""
        return self.index + 1 if self.running else 0
