

def test_emotion_detection() -> None:
    from leiyu_pet.caption_widget import emotion_of

    assert emotion_of("这也太离谱了！") == "exclaim"
    assert emotion_of("真的吗？") == "question"
    assert emotion_of("我想想…") == "ellipsis"
    assert emotion_of("今天天气不错") == "calm"
    assert emotion_of("") == "calm"


def test_typewriter_reveals_gradually() -> None:
    from PySide6.QtWidgets import QApplication

    from leiyu_pet.caption_widget import CaptionWidget

    QApplication.instance() or QApplication([])
    widget = CaptionWidget()
    widget.set_caption("雷军说了一段话")
    assert widget.visible_text() == ""
    widget._reveal_next()
    widget._reveal_next()
    assert widget.visible_text() == "雷军"
    widget.reveal_all()
    assert widget.visible_text() == "雷军说了一段话"
    assert widget.emotion == "calm"


def test_pulse_is_clamped() -> None:
    from PySide6.QtWidgets import QApplication

    from leiyu_pet.caption_widget import CaptionWidget

    QApplication.instance() or QApplication([])
    widget = CaptionWidget()
    widget.set_pulse(5.0)
    assert widget._pulse == 1.0
    widget.set_pulse(-3.0)
    assert widget._pulse == 0.0
