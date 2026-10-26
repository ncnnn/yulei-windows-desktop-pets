"""应用入口：装配单实例、配置、素材、运行时与托盘。"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from . import __version__

#: 判定"这是一个可用素材包"所需的根文件。
PACK_ROOT_FILES = ("lei.png", "yu.png", "clips.json", "clips-helium.json", "pairs.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="雷余双桌宠 Windows 版")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--reset", action="store_true", help="清除本地配置后以默认值启动")
    return parser


def looks_like_pack(root: Path) -> bool:
    """判断目录是否是一个完整的素材包根。"""
    return root.is_dir() and all((root / name).is_file() for name in PACK_ROOT_FILES)


def bundled_pack_root() -> Path | None:
    """返回随包素材目录。

    PyInstaller 冻结态经 ``sys._MEIPASS`` 定位；源码运行取仓库根的
    ``assets/default_pack``；同时兼容便携版把素材放在 exe 同级的情况。
    """
    from . import paths

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "default_pack")
    candidates.append(Path(__file__).resolve().parents[2] / "assets" / "default_pack")
    candidates.append(paths.exe_dir() / "assets" / "default_pack")
    for candidate in candidates:
        if looks_like_pack(candidate):
            return candidate
    return None


def resolve_pack():
    """按优先级解析可用素材包：随包默认包 → exe 同级 → 导入 store。

    全部无效时返回 ``None``，由调用方决定是否弹出导入向导。
    """
    from . import paths
    from .asset_importer import active_asset_root
    from .manifest import AssetValidationError, load_asset_pack

    candidates: list[Path] = []
    bundled = bundled_pack_root()
    if bundled is not None:
        candidates.append(bundled)
    exe_assets = paths.exe_dir() / "assets"
    if looks_like_pack(exe_assets):
        candidates.append(exe_assets)
    store_root = active_asset_root(paths.assets_store_dir())
    if store_root is not None:
        candidates.append(store_root)

    for root in candidates:
        try:
            return load_asset_pack(root)
        except AssetValidationError:
            continue
    return None


def apply_config(runtime, settings) -> None:
    """把配置下发到运行时与各窗口。"""
    runtime.set_volume(settings.volume)
    runtime.set_distance(settings.distance)

    controller = runtime.controller
    controller.set_voice_mode("helium" if settings.helium else "normal")
    controller.set_include_explicit(settings.include_explicit)
    controller.set_tilt_enabled(settings.tilt_enabled)

    runtime.set_role_visible("lei", settings.lei_visible)
    runtime.set_role_visible("yu", settings.yu_visible)

    for window in runtime.windows.values():
        window.set_locked(settings.lock_position)
        window.set_click_through(settings.click_through)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from PySide6.QtWidgets import QApplication, QDialog

    from . import autostart, config, paths

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if args.reset:
        with contextlib.suppress(OSError):
            paths.config_path().unlink()

    from .single_instance import SingleInstance

    single = SingleInstance(paths.base_dir())
    if not single.acquire():
        return 0

    cfg = config.load_config(paths.config_path())

    pack = resolve_pack()
    if pack is None:
        from .import_wizard import ImportWizard

        wizard = ImportWizard()
        accepted = wizard.exec() == QDialog.DialogCode.Accepted
        if not accepted or wizard.pack is None:
            single.close()
            return 0
        pack = wizard.pack

    from .runtime import PetRuntime
    from .settings_dialog import SettingsDialog
    from .tray import TrayManager

    runtime = PetRuntime(pack, show=True)
    apply_config(runtime, cfg)

    def open_settings() -> None:
        SettingsDialog(runtime, cfg).exec()
        with contextlib.suppress(OSError):
            config.save_config(cfg, paths.config_path())

    tray = TrayManager(runtime, cfg, on_open_settings=open_settings, on_quit=app.quit)
    tray.show()

    # 配置声明开机自启时确保注册表项存在（可能被安全软件清理）。
    autostart.set_enabled(bool(cfg.autostart))

    # 重复启动时新进程会向本实例发送 "show"，这里把两只桌宠都带出来。
    single.message_received.connect(lambda _message: runtime.show_all())

    def cleanup() -> None:
        with contextlib.suppress(OSError):
            config.save_config(cfg, paths.config_path())
        runtime.close()
        single.close()

    app.aboutToQuit.connect(cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
