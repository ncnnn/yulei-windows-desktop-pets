"""相声模式的纯逻辑测试：角色交替、问答配对与逐句推进。"""

import random

import pytest

from leiyu_pet.crosstalk import (
    BATTLE_END_VOLUME,
    BATTLE_START_VOLUME,
    DEFAULT_LINES,
    LINE_PRESETS,
    CrosstalkDirector,
    battle_multipliers,
    clamp_lines,
    commands_from_pairs,
    crosstalk_roles,
)
from leiyu_pet.models import DialoguePair, PlaybackCommand

#: 与 conftest 的素材一致：(问, 答) = (1,2) (3,4) ... (15,16)
PAIRS = [DialoguePair(pair_id, pair_id * 2 - 1, pair_id * 2) for pair_id in range(1, 9)]


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


def test_commands_from_pairs_are_strictly_alternating_and_paired() -> None:
    commands = commands_from_pairs(PAIRS, 6)

    assert [command.role for command in commands] == ["lei", "yu", "lei", "yu", "lei", "yu"]
    assert [command.clip_id for command in commands] == [1, 2, 3, 4, 5, 6]


def test_commands_from_pairs_walks_all_pairs_in_order_first() -> None:
    commands = commands_from_pairs(PAIRS, 16)
    expected = [clip for pair in PAIRS for clip in (pair.lei, pair.yu)]
    assert [command.clip_id for command in commands] == expected


def test_commands_from_pairs_shuffles_rounds_after_exhausting() -> None:
    """素材用完后整轮重排，但仍必须是成对的问答，不能各抽一句。"""
    commands = commands_from_pairs(PAIRS, 20, rng=random.Random(7))
    assert len(commands) == 20

    first_round = commands[:16]
    assert [command.clip_id for command in first_round] == [
        clip for pair in PAIRS for clip in (pair.lei, pair.yu)
    ]

    tail = commands[16:]
    assert [command.role for command in tail] == ["lei", "yu", "lei", "yu"]
    pairs = {(pair.lei, pair.yu) for pair in PAIRS}
    assert (tail[0].clip_id, tail[1].clip_id) in pairs
    assert (tail[2].clip_id, tail[3].clip_id) in pairs


def test_commands_from_pairs_rejects_empty_pack() -> None:
    with pytest.raises(ValueError):
        commands_from_pairs([], 4)


def test_commands_from_pairs_is_deterministic_with_seeded_rng() -> None:
    first = commands_from_pairs(PAIRS, 20, rng=random.Random(3))
    second = commands_from_pairs(PAIRS, 20, rng=random.Random(3))
    assert first == second


def test_battle_ladder_runs_from_20_to_70_percent() -> None:
    ladder = battle_multipliers(3)
    assert ladder[0] == pytest.approx(BATTLE_START_VOLUME)
    assert ladder[-1] == pytest.approx(BATTLE_END_VOLUME)
    assert ladder == sorted(ladder)
    assert battle_multipliers(1) == [BATTLE_END_VOLUME]

    for count in (2, 4, 6, 12):
        values = battle_multipliers(count)
        assert len(values) == count
        assert all(BATTLE_START_VOLUME <= value <= BATTLE_END_VOLUME for value in values)
