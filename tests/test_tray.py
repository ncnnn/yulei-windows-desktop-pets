"""TrayManager 测试（offscreen，不弹真实窗口）。"""

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_STUB_ROOT = Path(tempfile.mkdtemp(prefix="leiyu-tray-stub-"))


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
            self.crosstalk_lines = 6
            self.remember_position = True
            self.lei_pos = []
            self.yu_pos = []
            self.hotkeys_enabled = True
            self.check_updates = True
            self.reduce_motion = False
            self.version = 2
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
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from leiyu_pet import tray as tray_module  # noqa: E402
from leiyu_pet.autostart import is_enabled  # noqa: E402
from leiyu_pet.config import Config  # noqa: E402
from leiyu_pet.context_menu import ROLE_NAMES  # noqa: E402
from leiyu_pet.tray import ROLES, TrayManager  # noqa: E402

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
        self.crosstalk_lines = 6
        self.playback_rate = 1.0
        self.proximity = types.SimpleNamespace(distance=32.0)
        self.calls = []

    def play_solo(self, role, clip_id=None):
        self.calls.append(("play_solo", role, clip_id))

    def start_pair(self):
        self.calls.append(("start_pair",))

    def start_crosstalk(self, lines=None):
        self.calls.append(("start_crosstalk", lines))
        return True

    def set_crosstalk_lines(self, lines):
        self.calls.append(("set_crosstalk_lines", lines))
        self.crosstalk_lines = lines

    def stop_all(self):
        self.calls.append(("stop_all",))

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

    def set_rate(self, rate):
        self.calls.append(("set_rate", rate))
        self.playback_rate = rate

    def set_distance(self, value):
        self.calls.append(("set_distance", value))
        self.proximity.distance = value

    def update_proximity(self):
        self.calls.append(("update_proximity",))
        return True


class FakeRuntime:
    def __init__(self, volume=0.65, tilt=True):
        self.volume = volume
        self.windows = {
            "lei": FakeWindow(True, 220),
            "yu": FakeWindow(True, 220),
        }
        self.controller = FakeController()
        self.controller.tilt_enabled = tilt
        self.calls = []

    def set_volume(self, value):
        self.volume = min(max(float(value), 0.0), 1.0)
        self.calls.append(("set_volume", self.volume))

    def set_rate(self, rate):
        self.calls.append(("set_rate", rate))
        self.controller.playback_rate = rate

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


def _action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
    raise AssertionError(f"action {text!r} not found")


def _submenu(tray, title):
    for submenu in tray._submenus:
        if submenu.title() == title:
            return submenu
    raise AssertionError(f"submenu {title!r} not found")


def test_tray_builds_and_shows(app):
    runtime = FakeRuntime()
    config = Config()
    tray = TrayManager(runtime, config, on_open_settings=lambda: None)
    tray.show()

    assert tray._tray.isVisible()
    texts = [a.text() for a in tray._menu.actions()]
    assert f"显示/隐藏{ROLE_NAMES['lei']}桌宠" in texts
    assert f"显示/隐藏{ROLE_NAMES['yu']}桌宠" in texts
    assert "显示全部" in texts
    assert "设置" in texts
    assert "退出" in texts
    titles = {submenu.title() for submenu in tray._submenus}
    assert {"声音模式", "音量", "歪头距离", "人物大小", "雷军", "余承东"} <= titles

    child_menus = [sm for sm in tray._submenus if sm.title() in ROLE_NAMES.values()]
    assert len(child_menus) == 2


def test_playback_actions_call_controller(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    _action(tray._menu, f"{ROLE_NAMES['lei']}随机说一段").trigger()
    _action(tray._menu, f"{ROLE_NAMES['yu']}随机说一段").trigger()
    _action(tray._menu, "两人对话一句").trigger()
    _action(tray._menu, "停止播放").trigger()

    calls = [c[0] for c in runtime.controller.calls]
    assert calls == ["play_solo", "play_solo", "start_pair", "stop_all"]


def test_role_visibility_toggle(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    action = _action(tray._menu, f"显示/隐藏{ROLE_NAMES['lei']}桌宠")
    assert action.isChecked() is True
    action.trigger()
    assert runtime.windows["lei"].isVisible() is False
    assert ("set_role_visible", "lei", False) in runtime.calls


def test_volume_radio_sets_runtime_volume(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    volume_menu = _submenu(tray, "音量")
    _action(volume_menu, "50%").trigger()
    assert ("set_volume", 0.5) in runtime.calls


def test_distance_radio_sets_runtime_distance(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    distance_menu = _submenu(tray, "歪头距离")
    _action(distance_menu, "贴近（8）").trigger()
    assert ("set_distance", 8) in runtime.calls


def test_size_radio_sets_pet_size(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    lei_menu = _submenu(tray, ROLE_NAMES["lei"])
    _action(lei_menu, "小").trigger()
    assert ("set_pet_size", "lei", 170) in runtime.calls


def test_voice_mode_radio(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    voice_menu = _submenu(tray, "声音模式")
    _action(voice_menu, "1.5倍氦气版").trigger()
    assert runtime.controller.voice_mode == "helium"


def test_tilt_toggle(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    _action(tray._menu, "靠近时互相歪头").trigger()
    assert runtime.controller.tilt_enabled is False


def test_autostart_toggle_saves_config(app):
    runtime = FakeRuntime()
    config = Config()
    tray = TrayManager(runtime, config)
    tray.build_menu()

    _action(tray._menu, "开机自启").trigger()
    assert is_enabled() is True
    assert config.autostart is True
    assert config._saved


def test_autostart_failure_falls_back(app, monkeypatch):
    runtime = FakeRuntime()
    config = Config()
    tray = TrayManager(runtime, config)
    tray.build_menu()

    messages = []
    tray._tray.showMessage = lambda *args, **kwargs: messages.append(args)

    def _boom(enabled, exe_path=None):
        raise OSError("denied")

    monkeypatch.setattr(tray_module, "set_enabled", _boom)
    _action(tray._menu, "开机自启").trigger()

    assert config.autostart is False
    assert messages


def test_double_click_toggles_all(app):
    runtime = FakeRuntime()
    tray = TrayManager(runtime, Config())

    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert not runtime.windows["lei"].isVisible()
    assert not runtime.windows["yu"].isVisible()

    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert runtime.windows["lei"].isVisible()
    assert runtime.windows["yu"].isVisible()


def test_open_settings_callback(app):
    called = []
    tray = TrayManager(FakeRuntime(), Config(), on_open_settings=lambda: called.append(1))
    tray.build_menu()

    _action(tray._menu, "设置").trigger()
    assert called == [1]


def test_quit_callback(app):
    called = []
    tray = TrayManager(FakeRuntime(), Config(), on_quit=lambda: called.append(1))
    tray.build_menu()

    _action(tray._menu, "退出").trigger()
    assert called == [1]


def test_crosstalk_menu_starts_and_sets_lines(app):
    runtime = FakeRuntime()
    config = Config()
    tray = TrayManager(runtime, config)
    tray.build_menu()

    crosstalk_menu = _submenu(tray, "相声模式")
    _action(crosstalk_menu, "8 句").trigger()
    _action(crosstalk_menu, "开始（两只交替连续说）").trigger()

    assert ("set_crosstalk_lines", 8) in runtime.controller.calls
    assert config.crosstalk_lines == 8
    assert config._saved
    assert ("start_crosstalk", None) in runtime.controller.calls


def test_crosstalk_starts_after_showing_all(app):
    runtime = FakeRuntime()
    runtime.windows["yu"].setVisible(False)
    attempts = []

    def start_with_hidden_pet(lines=None):
        visible = all(runtime.windows[role].isVisible() for role in ROLES)
        attempts.append(visible)
        return visible

    runtime.controller.start_crosstalk = start_with_hidden_pet
    tray = TrayManager(runtime, Config())
    tray.build_menu()

    _action(_submenu(tray, "相声模式"), "开始（两只交替连续说）").trigger()

    assert attempts == [False, True]
    assert ("show_all",) in runtime.calls


def test_notify_shows_balloon(app):
    tray = TrayManager(FakeRuntime(), Config())
    messages = []
    tray._tray.showMessage = lambda *args, **kwargs: messages.append(args)

    tray.notify("新版本", "v1.2.0 可用")
    tray.notify("出错了", "详情见日志", warning=True)

    assert len(messages) == 2
