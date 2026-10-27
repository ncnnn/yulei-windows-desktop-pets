"""决斗特效窗口测试（offscreen，不弹真实窗口）。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt

from leiyu_pet.duel_effect import DUEL_DURATION, DUEL_SIZE, DuelEffect


def test_window_is_click_through_and_never_steals_focus(qapp) -> None:
    effect = DuelEffect()
    flags = effect.windowFlags()

    assert flags & Qt.WindowType.Tool
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert effect.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert effect.windowTitle() == "决斗特效"
    effect.close()


def test_play_centers_on_the_given_point(qapp) -> None:
    effect = DuelEffect()
    try:
        assert effect.play_at(QPoint(500, 400)) is True
        assert effect.playing is True
        assert effect.pos() == QPoint(500 - DUEL_SIZE // 2, 400 - DUEL_SIZE // 2)
    finally:
        effect.stop()
        effect.close()


def test_only_one_effect_at_a_time(qapp) -> None:
    effect = DuelEffect()
    try:
        assert effect.play_at(QPoint(100, 100)) is True
        assert effect.play_at(QPoint(200, 200)) is False
        assert effect.pos() == QPoint(100 - DUEL_SIZE // 2, 100 - DUEL_SIZE // 2)
    finally:
        effect.stop()
        effect.close()


def test_effect_finishes_after_its_duration(qapp) -> None:
    effect = DuelEffect()
    finished = []
    effect.finished.connect(lambda: finished.append(True))
    try:
        effect.play_at(QPoint(0, 0))
        steps = int(DUEL_DURATION / 0.016) + 5
        for _ in range(steps):
            effect._step(0.016)
        assert effect.playing is False
        assert effect.progress >= 1.0
        assert finished == [True]
    finally:
        effect.close()


def test_stop_hides_immediately(qapp) -> None:
    effect = DuelEffect()
    try:
        effect.play_at(QPoint(0, 0))
        effect.stop()
        assert effect.playing is False
    finally:
        effect.close()


def test_effect_eases_towards_a_moving_centre_then_freezes(qapp) -> None:
    target = [QPoint(500, 400)]
    effect = DuelEffect(center_provider=lambda: target[0])
    try:
        effect.play_at(QPoint(300, 300))
        start_x = effect.x()

        target[0] = QPoint(700, 400)
        for _ in range(5):
            effect._step(0.016)
        assert effect.x() > start_x  # 向新中点靠拢，但不是瞬间跳过去

        effect._progress = 0.7  # 进入淡出阶段
        frozen = effect.x()
        target[0] = QPoint(100, 100)
        for _ in range(5):
            effect._step(0.02)
        assert effect.x() == frozen
    finally:
        effect.stop()
        effect.close()
