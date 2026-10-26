"""ImportWizard 测试（offscreen，不弹真实窗口）。"""

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_STUB_ROOT = Path(tempfile.mkdtemp(prefix="leiyu-wizard-stub-"))


def _build_stub_modules():
    paths_mod = types.ModuleType("leiyu_pet.paths")
    paths_mod.assets_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.assets_store_dir = lambda: _STUB_ROOT / "assets"
    paths_mod.config_path = lambda: _STUB_ROOT / "config.json"
    paths_mod.is_portable = lambda: False
    return {"leiyu_pet.paths": paths_mod}


_STUBS = _build_stub_modules()
_SAVED_MODULES = {}
for _name, _mod in _STUBS.items():
    _SAVED_MODULES[_name] = sys.modules.get(_name)
    sys.modules[_name] = _mod

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from leiyu_pet import import_wizard as import_wizard_module  # noqa: E402
from leiyu_pet.import_wizard import ImportWizard  # noqa: E402

# 恢复 sys.modules，避免污染全局，影响依赖真实模块的其他测试
for _name, _mod in _STUBS.items():
    if _SAVED_MODULES[_name] is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _SAVED_MODULES[_name]


@pytest.fixture
def app():
    existing = QApplication.instance()
    application = existing if existing is not None else QApplication([])
    yield application


def test_should_show_when_no_asset(app, monkeypatch):
    monkeypatch.setattr(import_wizard_module, "active_asset_root", lambda store: None)
    assert ImportWizard.should_show() is True


def test_should_not_show_when_asset_present(app, monkeypatch):
    monkeypatch.setattr(
        import_wizard_module, "active_asset_root", lambda store: Path("/x")
    )
    assert ImportWizard.should_show() is False


def test_import_success_accepts(app, monkeypatch):
    fake_pack = object()
    monkeypatch.setattr(
        import_wizard_module, "import_asset_pack", lambda source, store: fake_pack
    )
    wizard = ImportWizard()
    wizard._import(Path("/some/source"))
    assert wizard.pack is fake_pack
    assert wizard.result() == QDialog.Accepted


def test_import_failure_shows_message_and_stays(app, monkeypatch):
    def _boom(source, store):
        raise import_wizard_module.AssetImportError("bad zip")

    monkeypatch.setattr(import_wizard_module, "import_asset_pack", _boom)
    monkeypatch.setattr(
        import_wizard_module.QMessageBox, "warning", lambda *args, **kwargs: None
    )

    wizard = ImportWizard()
    wizard._import(Path("/bad/source"))
    assert wizard.pack is None
    assert wizard.result() != QDialog.Accepted


def test_later_rejects(app):
    wizard = ImportWizard()
    wizard.reject()
    assert wizard.result() == QDialog.Rejected
