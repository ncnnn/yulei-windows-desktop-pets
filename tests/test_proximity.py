import math

from leiyu_pet.proximity import ProximityTracker, Rect, angle_for_delta, gap


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
