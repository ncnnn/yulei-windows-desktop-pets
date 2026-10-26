"""SettingsDialog 测试（offscreen，不弹真实窗口）。"""

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_STUB_ROOT = Path(tempfile.mkdtemp(prefix="leiyu-settings-stub-"))


def _build_stub_modules():
    config_mod = types.ModuleType("leiyu_pet.config")

    class Config:
        def __init__(self, **kwargs):
            self.volume = 0.65
            self.distance = 32
            self.tilt_enabled = True
            self.helium = False
            self.include_explicit = False
            self.autostart = False
            self.click_through = False
            self.lock_position = False
            self.lei_visible = True
            self.yu_visible = True
            self.version = 1
            self._saved = []
            for key, value in kwargs.items():
                setattr(self, key, value)

    def save_config(cfg, path):
        cfg._saved.append(path)

    config_mod.Config = Config
    config_mod.save_config = save_config

    paths_mod = types.ModuleType("leiyu_pet.paths")
    paths_mod.assets_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.assets_store_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.config_path = lambda: _STUB_ROOT / "config.json"
    paths_mod.is_portable = lambda: False

    autostart_mod = types.ModuleType("leiyu_pet.autostart")
    autostart_mod._state = {"enabled": False}

    def is_enabled(exe_path=None):
        return autostart_mod._state["enabled"]

    def set_enabled(enabled, exe_path=None):
        autostart_mod._state["enabled"] = bool(enabled)
        return True

    def self_check_requested_but_missing(config_autostart, exe_path=None):
        return bool(config_autostart) and not autostart_mod._state["enabled"]

    autostart_mod.is_enabled = is_enabled
    autostart_mod.set_enabled = set_enabled
    autostart_mod.self_check_requested_but_missing = (
        self_check_requested_but_missing
    )

    return {
        "leiyu_pet.config": config_mod,
        "leiyu_pet.paths": paths_mod,
        "leiyu_pet.autostart": autostart_mod,
    }


_STUBS = _build_stub_modules()
_SAVED_MODULES = {}
for _name, _mod in _STUBS.items():
    _SAVED_MODULES[_name] = sys.modules.get(_name)
    sys.modules[_name] = _mod

import pytest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QSlider,
)

from leiyu_pet.autostart import is_enabled  # noqa: E402
from leiyu_pet.config import Config  # noqa: E402
from leiyu_pet.settings_dialog import ROLES, SettingsDialog  # noqa: E402

# 恢复 sys.modules，避免污染全局，影响依赖真实模块的其他测试
for _name, _mod in _STUBS.items():
    if _SAVED_MODULES[_name] is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _SAVED_MODULES[_name]


class FakeWindow:
    def __init__(self, visible=True, size=220):
        self._visible = visible
        self.pet_size = size
        self._click_through = False

    def isVisible(self):
        return self._visible

    def setVisible(self, value):
        self._visible = bool(value)

    def set_pet_size(self, size):
        self.pet_size = size

    def set_click_through(self, value):
        self._click_through = bool(value)

    def click_through(self):
        return self._click_through


class FakeController:
    def __init__(self):
        self.voice_mode = "normal"
        self.include_explicit = False
        self.tilt_enabled = True
        self.proximity = types.SimpleNamespace(distance=32.0)
        self.calls = []

    def set_voice_mode(self, mode):
        self.calls.append(("set_voice_mode", mode))
        self.voice_mode = mode

    def set_include_explicit(self, value):
        self.calls.append(("set_include_explicit", value))
        self.include_explicit = bool(value)

    def set_tilt_enabled(self, value):
        self.calls.append(("set_tilt_enabled", value))
        self.tilt_enabled = bool(value)

    def set_volume(self, value):
        self.calls.append(("set_volume", value))

    def set_distance(self, value):
        self.calls.append(("set_distance", value))
        self.proximity.distance = value

    def update_proximity(self):
        self.calls.append(("update_proximity",))
        return True


class FakeRuntime:
    def __init__(self, volume=0.65):
        self.volume = volume
        self.windows = {
            "lei": FakeWindow(True, 220),
            "yu": FakeWindow(True, 220),
        }
        self.controller = FakeController()
        self.calls = []

    def set_volume(self, value):
        self.volume = min(max(float(value), 0.0), 1.0)
        self.calls.append(("set_volume", self.volume))

    def set_distance(self, value):
        self.calls.append(("set_distance", value))

    def set_pet_size(self, role, size):
        self.windows[role].set_pet_size(size)
        self.calls.append(("set_pet_size", role, size))

    def set_role_visible(self, role, visible):
        self.windows[role].setVisible(visible)
        self.calls.append(("set_role_visible", role, visible))

    def show_all(self):
        for role in ROLES:
            self.set_role_visible(role, True)
        self.calls.append(("show_all",))

    def toggle_role(self, role):
        self.set_role_visible(role, not self.windows[role].isVisible())

    def reset_position(self, role):
        self.calls.append(("reset_position", role))

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def app():
    existing = QApplication.instance()
    application = existing if existing is not None else QApplication([])
    yield application


def _label_of(dialog, widget):
    return dialog.layout().labelForField(widget)


def _slider(dialog, label):
    for widget in dialog.findChildren(QSlider):
        if _label_of(dialog, widget) is not None and _label_of(dialog, widget).text() == label:
            return widget
    raise AssertionError(f"slider {label!r} not found")


def _combo(dialog, label):
    for widget in dialog.findChildren(QComboBox):
        if _label_of(dialog, widget) is not None and _label_of(dialog, widget).text() == label:
            return widget
    raise AssertionError(f"combo {label!r} not found")


def _checkbox(dialog, text):
    for widget in dialog.findChildren(QCheckBox):
        if widget.text() == text:
            return widget
    raise AssertionError(f"checkbox {text!r} not found")


def test_widgets_exist(app):
    dialog = SettingsDialog(FakeRuntime(), Config())
    assert _slider(dialog, "音量") is not None
    assert _combo(dialog, "歪头距离") is not None
    assert _combo(dialog, "雷军大小") is not None
    assert _combo(dialog, "余承东大小") is not None
    assert _combo(dialog, "声音模式") is not None
    assert _checkbox(dialog, "靠近时互相歪头") is not None
    assert _checkbox(dialog, "显示粗口台词（第17段）") is not None
    assert _checkbox(dialog, "开机自启") is not None
    assert _checkbox(dialog, "鼠标穿透（点击穿透到桌面）") is not None
    assert _checkbox(dialog, "锁定位置（由主程序读取生效）") is not None


def test_volume_slider(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    slider = _slider(dialog, "音量")
    slider.setValue(50)
    assert ("set_volume", 0.5) in runtime.calls


def test_distance_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "歪头距离")
    combo.setCurrentIndex(combo.findData(8))
    assert ("set_distance", 8) in runtime.calls


def test_size_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "雷军大小")
    combo.setCurrentIndex(combo.findData(170))
    assert ("set_pet_size", "lei", 170) in runtime.calls


def test_voice_combo(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.calls.clear()

    combo = _combo(dialog, "声音模式")
    combo.setCurrentIndex(combo.findData("helium"))
    assert runtime.controller.voice_mode == "helium"


def test_tilt_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.controller.calls.clear()

    _checkbox(dialog, "靠近时互相歪头").setChecked(False)
    assert runtime.controller.tilt_enabled is False


def test_explicit_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())
    runtime.controller.calls.clear()

    _checkbox(dialog, "显示粗口台词（第17段）").setChecked(True)
    assert runtime.controller.include_explicit is True


def test_autostart_checkbox_saves(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _checkbox(dialog, "开机自启").setChecked(True)
    assert is_enabled() is True
    assert config.autostart is True
    assert config._saved


def test_click_through_checkbox(app):
    runtime = FakeRuntime()
    dialog = SettingsDialog(runtime, Config())

    _checkbox(dialog, "鼠标穿透（点击穿透到桌面）").setChecked(True)
    assert runtime.windows["lei"].click_through() is True
    assert runtime.windows["yu"].click_through() is True


def test_lock_checkbox_saves(app):
    runtime = FakeRuntime()
    config = Config()
    dialog = SettingsDialog(runtime, config)

    _checkbox(dialog, "锁定位置（由主程序读取生效）").setChecked(True)
    assert config.lock_position is True
    assert config._saved
