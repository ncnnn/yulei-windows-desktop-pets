from __future__ import annotations

from pathlib import Path

from leiyu_pet import __main__ as entry
from leiyu_pet import asset_importer, paths
from leiyu_pet.config import Config


class FakeWindow:
    def __init__(self) -> None:
        self.locked: bool | None = None
        self.click_through: bool | None = None

    def set_locked(self, value: bool) -> None:
        self.locked = value

    def set_click_through(self, value: bool) -> None:
        self.click_through = value


class FakeController:
    def __init__(self) -> None:
        self.calls: dict[str, object] = {}

    def set_voice_mode(self, mode: str) -> None:
        self.calls["voice_mode"] = mode

    def set_include_explicit(self, value: bool) -> None:
        self.calls["include_explicit"] = value

    def set_tilt_enabled(self, value: bool) -> None:
        self.calls["tilt_enabled"] = value


class FakeRuntime:
    def __init__(self) -> None:
        self.volume: float | None = None
        self.distance: float | None = None
        self.visible: dict[str, bool] = {}
        self.windows = {"lei": FakeWindow(), "yu": FakeWindow()}
        self.controller = FakeController()

    def set_volume(self, value: float) -> None:
        self.volume = value

    def set_distance(self, value: float) -> None:
        self.distance = value

    def set_role_visible(self, role: str, visible: bool) -> None:
        self.visible[role] = visible


def test_parser_defaults() -> None:
    args = entry.build_parser().parse_args([])
    assert args.reset is False


def test_parser_reset_flag() -> None:
    args = entry.build_parser().parse_args(["--reset"])
    assert args.reset is True


def test_looks_like_pack(tmp_path: Path, asset_pack_factory) -> None:
    pack = asset_pack_factory()
    assert entry.looks_like_pack(pack) is True
    assert entry.looks_like_pack(tmp_path / "missing") is False
    empty = tmp_path / "empty"
    empty.mkdir()
    assert entry.looks_like_pack(empty) is False


def test_apply_config_propagates_to_runtime_and_windows() -> None:
    runtime = FakeRuntime()
    cfg = Config(
        volume=0.3,
        distance=80,
        helium=True,
        include_explicit=True,
        tilt_enabled=False,
        lei_visible=False,
        yu_visible=True,
        lock_position=True,
        click_through=True,
    )
    entry.apply_config(runtime, cfg)

    assert runtime.volume == 0.3
    assert runtime.distance == 80
    assert runtime.controller.calls["voice_mode"] == "helium"
    assert runtime.controller.calls["include_explicit"] is True
    assert runtime.controller.calls["tilt_enabled"] is False
    assert runtime.visible == {"lei": False, "yu": True}
    assert runtime.windows["lei"].locked is True
    assert runtime.windows["yu"].locked is True
    assert runtime.windows["lei"].click_through is True


def _isolate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path / "exe")
    monkeypatch.setattr(paths, "assets_store_dir", lambda: tmp_path / "store")
    monkeypatch.setattr(asset_importer, "active_asset_root", lambda store: None)


def test_resolve_pack_prefers_bundled(monkeypatch, tmp_path: Path, asset_pack_factory) -> None:
    pack_dir = asset_pack_factory()
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(entry, "bundled_pack_root", lambda: pack_dir)

    pack = entry.resolve_pack()

    assert pack is not None
    assert len(pack.normal_clips) == 17
    assert pack.root == pack_dir.resolve()


def test_resolve_pack_falls_back_to_store(monkeypatch, tmp_path: Path, asset_pack_factory) -> None:
    pack_dir = asset_pack_factory()
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(entry, "bundled_pack_root", lambda: None)
    monkeypatch.setattr(asset_importer, "active_asset_root", lambda store: pack_dir)

    pack = entry.resolve_pack()

    assert pack is not None
    assert pack.root == pack_dir.resolve()


def test_resolve_pack_returns_none_when_absent(monkeypatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(entry, "bundled_pack_root", lambda: None)

    assert entry.resolve_pack() is None
