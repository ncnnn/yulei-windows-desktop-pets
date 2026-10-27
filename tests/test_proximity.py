import math

from leiyu_pet.proximity import (
    ProximityTracker,
    Rect,
    angle_for_delta,
    gap,
    overlap_area,
    overlap_ratio,
)


def test_gap_handles_overlap_and_diagonal_distance() -> None:
    assert gap(Rect(0, 0, 10, 10), Rect(5, 5, 10, 10)) == 0
    assert math.isclose(gap(Rect(0, 0, 10, 10), Rect(13, 14, 10, 10)), 5.0)


def test_proximity_uses_hysteresis() -> None:
    tracker = ProximityTracker(distance=32, hysteresis=24)
    lei = Rect(0, 0, 100, 100)
    assert tracker.update(lei, Rect(132, 0, 100, 100)) is True
    assert tracker.update(lei, Rect(155, 0, 100, 100)) is True
    assert tracker.update(lei, Rect(157, 0, 100, 100)) is False


def test_tilt_angles_point_towards_each_other() -> None:
    tracker = ProximityTracker(near=True)
    lei = Rect(0, 0, 100, 100)
    yu = Rect(120, 0, 100, 100)
    assert tracker.tilt_angles(lei, yu) == (-0.2, 0.2)
    assert angle_for_delta(0) == -0.2
    assert tracker.tilt_angles(lei, yu, enabled=False) == (0.0, 0.0)


def test_overlap_area_and_ratio() -> None:
    a = Rect(0, 0, 100, 100)
    assert overlap_area(a, Rect(50, 50, 100, 100)) == 2500
    assert overlap_ratio(a, Rect(50, 50, 100, 100)) == 0.25
    assert overlap_area(a, Rect(200, 200, 50, 50)) == 0
    assert overlap_ratio(a, Rect(200, 200, 50, 50)) == 0


def test_overlap_ratio_is_capped_and_handles_empty() -> None:
    a = Rect(0, 0, 100, 100)
    assert overlap_ratio(a, Rect(0, 0, 100, 100)) == 1.0
    assert overlap_ratio(a, Rect(0, 0, 20, 20)) == 1.0
    assert overlap_ratio(Rect(0, 0, 0, 0), a) == 0.0
