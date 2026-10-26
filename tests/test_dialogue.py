from leiyu_pet.dialogue import DialogueController, DialogueStage
from leiyu_pet.models import DialoguePair, PlaybackCommand


def test_dialogue_always_runs_lei_then_yu() -> None:
    controller = DialogueController()
    pair = DialoguePair(1, 3, 4)
    assert controller.start(pair) == PlaybackCommand("lei", 3)
    assert controller.stage == DialogueStage.LEI
    assert controller.finished("yu", 4) is None
    assert controller.finished("lei", 3) == PlaybackCommand("yu", 4)
    assert controller.finished("yu", 4) is None
    assert controller.stage == DialogueStage.DONE


def test_cancel_clears_active_pair() -> None:
    controller = DialogueController()
    controller.start(DialoguePair(1, 1, 2))
    controller.cancel()
    assert controller.stage == DialogueStage.CANCELLED
    assert controller.pair is None
    assert not controller.active
