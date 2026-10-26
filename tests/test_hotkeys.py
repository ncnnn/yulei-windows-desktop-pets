"""全局热键解析与降级行为测试（不真的占用系统热键）。"""

import sys

import pytest

from leiyu_pet.hotkeys import (
    DEFAULT_BINDINGS,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    HotkeyError,
    HotkeyManager,
    describe_binding,
    parse_binding,
)


def test_parse_ctrl_alt_h() -> None:
    modifiers, key = parse_binding("ctrl+alt+h")
    assert modifiers == MOD_CONTROL | MOD_ALT
    assert key == ord("H")


def test_parse_is_case_insensitive_and_order_free() -> None:
    assert parse_binding("Alt+SHIFT+k") == parse_binding("shift+alt+K")


def test_parse_digit_and_function_keys() -> None:
    assert parse_binding("ctrl+1")[1] == ord("1")
    assert parse_binding("ctrl+f5")[1] == 0x74
    assert parse_binding("ctrl+space")[1] == 0x20


def test_parse_rejects_bad_specs() -> None:
    for spec in ("", "ctrl", "h", "ctrl+alt+unknown", "ctrl+f25"):
        with pytest.raises(HotkeyError):
            parse_binding(spec)


def test_default_bindings_are_valid() -> None:
    assert set(DEFAULT_BINDINGS) == {"toggle_visible", "crosstalk", "random_line", "stop"}
    for spec in DEFAULT_BINDINGS.values():
        assert parse_binding(spec)


def test_describe_binding() -> None:
    assert describe_binding("ctrl+alt+h") == "Ctrl+Alt+H"
    assert describe_binding("ctrl+f5") == "Ctrl+F5"


def test_manager_reports_failed_bindings_without_crashing() -> None:
    manager = HotkeyManager({"toggle_visible": "ctrl+alt+h"})
    assert manager.failed == {}
    if sys.platform != "win32":
        assert manager.install() == 0


def test_uninstall_is_idempotent() -> None:
    manager = HotkeyManager()
    manager.uninstall()
    manager.uninstall()
    assert manager.failed == {}


def test_triggered_signal_carries_action() -> None:
    manager = HotkeyManager()
    received = []
    manager.triggered.connect(received.append)
    manager._ids = {1: "crosstalk"}
    manager._dispatch(1)
    manager._dispatch(999)
    assert received == ["crosstalk"]
    assert MOD_SHIFT  # 常量存在性
