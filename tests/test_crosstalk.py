"""相声模式的纯逻辑测试：角色交替、问答配对与逐句推进。"""

import random
from dataclasses import dataclass
from pathlib import Path

import pytest

from leiyu_pet.crosstalk import (
    DEFAULT_LINES,
    LINE_PRESETS,
    CrosstalkDirector,
    clamp_lines,
    commands_from_pairs,
    crosstalk_roles,
    crosstalk_script,
)
from leiyu_pet.manifest import load_asset_pack
from leiyu_pet.models import DialoguePair, PlaybackCommand, Role

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




@dataclass(frozen=True)
class _Clip:
    id: int
    role: Role
    duration: float
    text: str = ""


@dataclass(frozen=True)
class _Pack:
    pairs: tuple[DialoguePair, ...]
    normal_clips: tuple[_Clip, ...]


def _script_pack() -> _Pack:
    """一段「两段正剧 + 两组短句副歌 + 一句收尾」的素材。"""
    return _Pack(
        pairs=(
            DialoguePair(1, 1, 2),
            DialoguePair(2, 3, 4),
            DialoguePair(6, 11, 12),
            DialoguePair(7, 13, 14),
        ),
        normal_clips=(
            _Clip(1, "lei", 3.0),
            _Clip(2, "yu", 4.0),
            _Clip(3, "lei", 6.0),
            _Clip(4, "yu", 5.0),
            _Clip(11, "lei", 0.9),
            _Clip(12, "yu", 0.4),
            _Clip(13, "lei", 0.9),
            _Clip(14, "yu", 0.4),
            _Clip(17, "lei", 1.7, "收尾"),
        ),
    )


def test_script_ends_on_the_unreferenced_punchline() -> None:
    """最后一句必须是收尾梗（那句没有问答搭档的台词）。"""
    script = crosstalk_script(_script_pack(), 20)

    assert len(script) == 20
    assert script[-1].clip_id == 17
    assert script[-1].role == "lei"


def test_script_plays_the_story_then_loops_the_short_chorus() -> None:
    """正剧问答说完 → 「总有机会 / 追不上」来回 → 收尾。"""
    script = crosstalk_script(_script_pack(), 20)

    assert [(c.role, c.clip_id) for c in script[:4]] == [
        ("lei", 1),
        ("yu", 2),
        ("lei", 3),
        ("yu", 4),
    ]
    # 中段是副歌短句来回，且始终是一问一答。
    chorus = {(11, "lei"), (12, "yu"), (13, "lei"), (14, "yu")}
    assert {(c.clip_id, c.role) for c in script[4:19]} == chorus
    for index in range(4, 19):
        assert script[index].role == ("lei" if (index - 4) % 2 == 0 else "yu")


def test_short_counts_stay_inside_the_story() -> None:
    """句数还没到副歌段时，就只播正剧，不硬凑。"""
    script = crosstalk_script(_script_pack(), 3)

    assert [(c.role, c.clip_id) for c in script] == [("lei", 1), ("yu", 2), ("lei", 3)]


def test_script_without_a_punchline_fills_up_with_the_chorus() -> None:
    """素材里没有孤立台词时，副歌填满句数，不留下半截段子。"""
    pack = _script_pack()
    pack = _Pack(pack.pairs, tuple(c for c in pack.normal_clips if c.id != 17))

    script = crosstalk_script(pack, 10)

    assert len(script) == 10
    assert all(command.clip_id != 17 for command in script)


def test_script_without_a_chorus_repeats_the_story() -> None:
    """素材没有短句副歌时，用正剧问答循环补齐，绝不返回半截剧本。"""
    pack = _script_pack()
    pack = _Pack(
        tuple(pair for pair in pack.pairs if pair.id <= 2),
        tuple(c for c in pack.normal_clips if c.id in (1, 2, 3, 4, 17)),
    )

    script = crosstalk_script(pack, 8)

    assert len(script) == 8
    assert script[-1].clip_id == 17


def test_real_asset_pack_script_matches_the_intended_routine() -> None:
    """真实素材：20 句，倒数第二句是「总有机会」，收尾是那句爆粗。"""
    root = Path(__file__).resolve().parents[1] / "assets" / "default_pack"
    if not root.is_dir():
        pytest.skip("仓库素材不在，跳过剧本结构检查")
    pack = load_asset_pack(root)

    script = crosstalk_script(pack, 20)

    assert len(script) == 20
    assert pack.clip("normal", script[9].clip_id).text.startswith("发布了全新一代")
    assert pack.clip("normal", script[-2].clip_id).text == "总有机会。"
    assert "捣乱" in pack.clip("normal", script[-1].clip_id).text
