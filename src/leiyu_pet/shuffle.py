"""抽完一轮再重洗、且跨轮不立即重复的随机袋。"""

from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Generic, TypeVar

T = TypeVar("T")


class ShuffleBag(Generic[T]):
    def __init__(self, values: Iterable[T], *, rng: random.Random | None = None):
        self._values = tuple(values)
        if not self._values:
            raise ValueError("随机袋不能为空")
        self._rng = rng or random.Random()
        self._remaining: list[T] = []
        self._last: T | None = None

    def _refill(self) -> None:
        self._remaining = list(self._values)
        self._rng.shuffle(self._remaining)
        if (
            len(self._remaining) > 1
            and self._last is not None
            and self._remaining[-1] == self._last
        ):
            self._remaining[-1], self._remaining[0] = (
                self._remaining[0],
                self._remaining[-1],
            )

    def next(self) -> T:
        if not self._remaining:
            self._refill()
        value = self._remaining.pop()
        self._last = value
        return value

    def reset(self) -> None:
        self._remaining.clear()
        self._last = None
