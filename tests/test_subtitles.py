from leiyu_pet.models import Clip, ClipLine
from leiyu_pet.subtitles import caption_at


def test_caption_switches_by_start_time_and_holds_after_end() -> None:
    clip = Clip(
        1,
        "lei",
        "第一句\n第二句",
        "lei-01.mp3",
        2.0,
        (ClipLine(0, 1, "第一句"), ClipLine(1, 2, "第二句")),
    )
    assert caption_at(clip, 0.5) == "第一句"
    assert caption_at(clip, 1.0) == "第二句"
    assert caption_at(clip, 2.3) == "第二句"
    assert caption_at(clip, 2.41) == ""
    assert caption_at(clip, -0.1) == ""
