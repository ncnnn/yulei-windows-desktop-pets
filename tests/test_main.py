from __future__ import annotations

from pathlib import Path

from leiyu_pet import __main__ as entry
from leiyu_pet import asset_importer, paths
from leiyu_pet.config import Config


class FakeWindow:
    def __init__(self) -> None:
        self.locked: bool | None = None
        self.click_through: bool | None = None
        self.reduce_motion: bool | None = None

    def set_locked(self, value: bool) -> None:
        self.locked = value

    def set_click_through(self, value: bool) -> None:
        self.click_through = value

    def set_reduce_motion(self, value: bool) -> None:
        self.reduce_motion = value


class FakeController:
    def __init__(self) -> None:
        self.calls: dict[str, object] = {}

    def set_voice_mode(self, mode: str) -> None:
        self.calls["voice_mode"] = mode

    def set_include_explicit(self, value: bool) -> None:
        self.calls["include_explicit"] = value

    def set_tilt_enabled(self, value: bool) -> None:
        self.calls["tilt_enabled"] = value

    def set_crosstalk_lines(self, value: int) -> None:
        self.calls["crosstalk_lines"] = value

    def set_overlap_easter_egg(self, value: bool) -> None:
        self.calls["overlap_easter_egg"] = value


class FakeAssistant:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}
        self.quiet = None

    def configure(self, **kwargs) -> None:
        self.config = dict(kwargs)

    def set_quiet_checker(self, checker) -> None:
        self.quiet = checker


class FakeRuntime:
    def __init__(self) -> None:
        self.volume: float | None = None
        self.distance: float | None = None
        self.visible: dict[str, bool] = {}
        self.sizes: dict[str, int] = {}
        self.rate: float | None = None
        self.opacity: float | None = None
        self.caption_font_size: int | None = None
        self.always_on_top: bool | None = None
        self.wander: tuple[bool, int] | None = None
        self.windows = {"lei": FakeWindow(), "yu": FakeWindow()}
        self.controller = FakeController()
        self.assistant = FakeAssistant()

    def set_volume(self, value: float) -> None:
        self.volume = value

    def set_distance(self, value: float) -> None:
        self.distance = value

    def set_role_visible(self, role: str, visible: bool) -> None:
        self.visible[role] = visible

    def set_pet_size(self, role: str, size: int) -> None:
        self.sizes[role] = size

    def set_rate(self, rate: float) -> None:
        self.rate = rate

    def set_opacity(self, value: float) -> None:
        self.opacity = value

    def set_caption_font_size(self, value: int) -> None:
        self.caption_font_size = value

    def set_always_on_top(self, value: bool) -> None:
        self.always_on_top = value

    def set_wander_enabled(self, enabled: bool, interval_seconds: int | None = None) -> None:
        self.wander = (bool(enabled), int(interval_seconds or 0))


def test_parser_defaults() -> None:
    args = entry.build_parser().parse_args([])
    assert args.reset is False
    assert args.selftest_audio is False


def test_parser_selftest_audio_flag() -> None:
    args = entry.build_parser().parse_args(["--selftest-audio"])
    assert args.selftest_audio is True


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
        crosstalk_lines=8,
        reduce_motion=True,
    )
    entry.apply_config(runtime, cfg)

    assert runtime.volume == 0.3
    assert runtime.distance == 80
    assert runtime.controller.calls["voice_mode"] == "helium"
    assert runtime.controller.calls["include_explicit"] is True
    assert runtime.controller.calls["tilt_enabled"] is False
    assert runtime.controller.calls["crosstalk_lines"] == 8
    assert runtime.visible == {"lei": False, "yu": True}
    assert runtime.windows["lei"].locked is True
    assert runtime.windows["yu"].locked is True
    assert runtime.windows["lei"].click_through is True
    assert runtime.windows["yu"].reduce_motion is True

    assert runtime.opacity == cfg.opacity
    assert runtime.caption_font_size == cfg.caption_font_size
    assert runtime.always_on_top is cfg.always_on_top
    assert runtime.wander == (cfg.wander_enabled, cfg.wander_interval_seconds)
    assert runtime.controller.calls["overlap_easter_egg"] is cfg.overlap_easter_egg
    assert runtime.assistant.config["hourly"] is cfg.hourly_chime
    assert runtime.assistant.quiet is not None


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


def test_resolve_pack_reports_validation_error(
    monkeypatch, tmp_path: Path, asset_pack_factory
) -> None:
    pack_dir = asset_pack_factory()
    (pack_dir / "clips.json").write_text("{}", encoding="utf-8")
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(entry, "bundled_pack_root", lambda: pack_dir)

    problems: list[str] = []
    assert entry.resolve_pack(problems) is None
    assert problems, "素材损坏时应记录失败原因"
