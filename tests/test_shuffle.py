import random

import pytest

from leiyu_pet.shuffle import ShuffleBag


def test_shuffle_bag_has_no_duplicates_within_round() -> None:
    bag = ShuffleBag(range(6), rng=random.Random(7))
    first = [bag.next() for _ in range(6)]
    second = [bag.next() for _ in range(6)]
    assert sorted(first) == list(range(6))
    assert sorted(second) == list(range(6))
    assert first[-1] != second[0]


def test_shuffle_bag_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        ShuffleBag([])
