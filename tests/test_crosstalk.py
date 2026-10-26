"""相声模式的纯逻辑测试：角色交替与逐句推进。"""

import pytest

from leiyu_pet.crosstalk import (
    DEFAULT_LINES,
    LINE_PRESETS,
    CrosstalkDirector,
    clamp_lines,
    crosstalk_roles,
)
from leiyu_pet.models import PlaybackCommand


def test_alternating_roles_start_with_lei() -> None:
    assert crosstalk_roles(4) == ["lei", "yu", "lei", "yu"]


def test_alternating_roles_start_with_yu() -> None:
    assert crosstalk_roles(3, lead="yu") == ["yu", "lei", "yu"]


def test_lines_are_clamped() -> None:
    assert clamp_lines(1) == 2
    assert clamp_lines(99) == 20
    assert clamp_lines("not-a-number") == DEFAULT_LINES
    assert len(crosstalk_roles(1)) == 2


def test_presets_are_inside_range() -> None:
    for preset in LINE_PRESETS:
        assert 2 <= preset <= 20
        assert len(crosstalk_roles(preset)) == preset


def test_director_walks_through_all_lines() -> None:
    commands = [PlaybackCommand("lei", 1), PlaybackCommand("yu", 2), PlaybackCommand("lei", 3)]
    director = CrosstalkDirector()

    first = director.start(commands)
    assert first == commands[0]
    assert director.running is True
    assert director.position == 1
    assert director.remaining == 3

    second = director.finished("lei", 1)
    assert second == commands[1]
    assert director.position == 2

    third = director.finished("yu", 2)
    assert third == commands[2]

    assert director.finished("lei", 3) is None
    assert director.running is False
    assert director.remaining == 0


def test_director_ignores_unrelated_finish_events() -> None:
    commands = [PlaybackCommand("lei", 1), PlaybackCommand("yu", 2)]
    director = CrosstalkDirector()
    director.start(commands)

    assert director.finished("yu", 2) is None
    assert director.finished("lei", 99) is None
    assert director.running is True
    assert director.position == 1


def test_director_cancel_stops_sequence() -> None:
    director = CrosstalkDirector()
    director.start([PlaybackCommand("lei", 1), PlaybackCommand("yu", 2)])
    director.cancel()

    assert director.running is False
    assert director.finished("lei", 1) is None
    assert director.position == 0


def test_director_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError):
        CrosstalkDirector().start([])
