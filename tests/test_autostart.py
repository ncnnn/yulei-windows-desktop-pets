"""autostart 模块测试（mock winreg，不写真实注册表）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from leiyu_pet import autostart


class FakeReg:
    """内存版 Run 键，模拟 winreg 的相关 API。"""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    REG_SZ = 2

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def OpenKey(self, root, key, reserved=0, access=0):  # noqa: N802
        return self

    def __enter__(self):  # noqa: N802
        return self

    def __exit__(self, *exc):  # noqa: N802
        return False

    def QueryValueEx(self, key, name):  # noqa: N802
        if name in self.data:
            return (self.data[name], self.REG_SZ)
        raise OSError("not found")

    def SetValueEx(self, key, name, reserved, type_, value):  # noqa: N802
        self.data[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        self.data.pop(name, None)


@pytest.fixture
def fake_reg(monkeypatch: pytest.MonkeyPatch) -> FakeReg:
    reg = FakeReg()
    monkeypatch.setattr(autostart, "winreg", reg)
    return reg


def test_is_enabled_false_when_absent(fake_reg: FakeReg) -> None:
    assert autostart.is_enabled() is False


def test_is_enabled_true_when_value_contains_exe(fake_reg: FakeReg, tmp_path: Path) -> None:
    exe = tmp_path / "myapp.exe"
    fake_reg.data[autostart.VALUE_NAME] = autostart._command(exe)
    assert autostart.is_enabled(exe) is True


def test_is_enabled_default_uses_sys_executable(fake_reg: FakeReg) -> None:
    fake_reg.data[autostart.VALUE_NAME] = autostart._command(Path(sys.executable))
    assert autostart.is_enabled() is True


def test_set_enabled_roundtrip(fake_reg: FakeReg, tmp_path: Path) -> None:
    exe = tmp_path / "myapp.exe"
    assert autostart.set_enabled(True, exe) is True
    assert autostart.is_enabled(exe) is True
    assert fake_reg.data[autostart.VALUE_NAME] == autostart._command(exe)


def test_set_enabled_false_removes_value(fake_reg: FakeReg, tmp_path: Path) -> None:
    exe = tmp_path / "myapp.exe"
    autostart.set_enabled(True, exe)
    assert autostart.set_enabled(False, exe) is True
    assert autostart.is_enabled(exe) is False


def test_remove_is_idempotent(fake_reg: FakeReg) -> None:
    assert autostart.remove() is None
    assert autostart.is_enabled() is False


def test_self_check_logic(fake_reg: FakeReg, tmp_path: Path) -> None:
    exe = tmp_path / "myapp.exe"
    assert autostart.self_check_requested_but_missing(True, exe) is True
    autostart.set_enabled(True, exe)
    assert autostart.self_check_requested_but_missing(True, exe) is False
    assert autostart.self_check_requested_but_missing(False, exe) is False


def test_command_quotes_paths_with_spaces(tmp_path: Path) -> None:
    exe = tmp_path / "with space" / "app.exe"
    command = autostart._command(exe)
    assert '"' in command
    assert str(exe) in command


def test_non_windows_safe_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(autostart, "winreg", None)
    exe = tmp_path / "app.exe"
    assert autostart.is_enabled(exe) is False
    assert autostart.set_enabled(True, exe) is False
    assert autostart.self_check_requested_but_missing(True, exe) is True
