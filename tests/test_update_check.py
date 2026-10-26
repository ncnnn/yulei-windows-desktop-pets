"""更新检查的版本比较与信号行为。"""

import pytest

from leiyu_pet.update_check import UpdateChecker, is_newer, parse_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v1.1.0", (1, 1, 0)),
        ("1.0", (1, 0)),
        ("release-2024-10", (2024, 10)),
        ("", (0,)),
        ("abc", (0,)),
    ],
)
def test_parse_version(text, expected) -> None:
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    ("current", "latest", "newer"),
    [
        ("1.0.1", "1.1.0", True),
        ("1.1.0", "1.1.0", False),
        ("1.1.0", "v1.1.0", False),
        ("1.1.0", "1.0.9", False),
        ("1.0", "1.0.1", True),
        ("v1.2", "v1.10", True),
    ],
)
def test_is_newer(current, latest, newer) -> None:
    assert is_newer(current, latest) is newer


def test_checker_holds_current_version() -> None:
    checker = UpdateChecker("1.1.0")
    assert checker.current_version == "1.1.0"


def test_update_available_signal() -> None:
    checker = UpdateChecker("1.1.0")
    received = []
    checker.update_available.connect(lambda tag, url: received.append((tag, url)))
    checker.update_available.emit("v1.2.0", "https://example.com")
    assert received == [("v1.2.0", "https://example.com")]
