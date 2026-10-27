"""paths 模块测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from leiyu_pet import paths


def _set_frozen_exe(monkeypatch: pytest.MonkeyPatch, exe: Path) -> None:
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))


def test_exe_dir_frozen_uses_executable_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "bin" / "app.exe"
    exe.parent.mkdir()
    _set_frozen_exe(monkeypatch, exe)
    assert paths.exe_dir() == exe.parent


def test_exe_dir_source_uses_module_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths.sys, "frozen", False, raising=False)
    assert paths.exe_dir() == Path(paths.__file__).resolve().parent


def test_is_portable_reflects_ini(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    _set_frozen_exe(monkeypatch, exe_dir / "app.exe")
    assert paths.is_portable() is False
    (exe_dir / "portable.ini").write_text("", encoding="utf-8")
    assert paths.is_portable() is True


def test_base_dir_portable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    _set_frozen_exe(monkeypatch, exe_dir / "app.exe")
    (exe_dir / "portable.ini").write_text("", encoding="utf-8")
    result = paths.base_dir()
    assert result == exe_dir / "data"
    assert result.is_dir()


def test_base_dir_installed_uses_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    result = paths.base_dir()
    assert result == tmp_path / "appdata" / paths.APP_NAME
    assert result.is_dir()


def test_base_dir_falls_back_to_localappdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    result = paths.base_dir()
    assert result == tmp_path / "local" / paths.APP_NAME
    assert result.is_dir()


def test_config_and_log_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    base = paths.base_dir()
    assert paths.config_path() == base / "config.json"
    assert paths.log_path() == base / "pet.log"


def test_assets_dir_bundled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    (exe_dir / "assets").mkdir(parents=True)
    (exe_dir / "assets" / "lei.png").write_bytes(b"x")
    (exe_dir / "assets" / "yu.png").write_bytes(b"x")
    _set_frozen_exe(monkeypatch, exe_dir / "app.exe")
    result = paths.assets_dir()
    assert result == exe_dir / "assets"
    assert result.is_dir()


def test_assets_dir_import_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(paths.sys, "frozen", False, raising=False)
    result = paths.assets_dir()
    assert result == paths.base_dir() / "assets"
    assert result.is_dir()


def test_assets_store_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    result = paths.assets_store_dir()
    assert result == paths.base_dir() / "assets"
    assert result.is_dir()


def test_app_icon_path_finds_the_repo_icon() -> None:
    """源码运行时图标取自仓库 packaging/；打包后由 _MEIPASS 提供。"""
    path = paths.app_icon_path()
    assert path is not None
    assert path.is_file()
    assert path.suffix.lower() == ".ico"
