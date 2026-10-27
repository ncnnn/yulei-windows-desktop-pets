"""应用入口：装配单实例、配置、素材、运行时、热键、托盘与更新检查。"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__

#: 判定"这是一个可用素材包"所需的根文件。
PACK_ROOT_FILES = ("lei.png", "yu.png", "clips.json", "clips-helium.json", "pairs.json")

LOGGER = logging.getLogger("leiyu_pet")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="雷余双桌宠 Windows 版")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--reset", action="store_true", help="清除本地配置后以默认值启动")
    parser.add_argument(
        "--selftest-audio",
        action="store_true",
        help="检查音频解码后端并试播一段，输出 JSON 后退出",
    )
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


def resolve_pack(report: list[str] | None = None):
    """按优先级解析可用素材包：随包默认包 → exe 同级 → 导入 store。

    全部无效时返回 ``None``，由调用方决定是否弹出导入向导。校验失败的原因会
    写进 ``report`` 并记日志——以前这里静默 continue，用户只看到导入向导却不
    知道素材哪里坏了。
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
        except AssetValidationError as exc:
            message = f"{root}：{exc}"
            if report is not None:
                report.append(message)
            LOGGER.warning("素材校验失败 %s", message)
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
    controller.set_crosstalk_lines(settings.crosstalk_lines)
    controller.set_overlap_easter_egg(settings.overlap_easter_egg)
    controller.set_overlap_trigger_gap(settings.overlap_trigger_gap)

    runtime.set_pet_size("lei", settings.lei_size)
    runtime.set_pet_size("yu", settings.yu_size)
    runtime.set_rate(settings.playback_rate)
    runtime.set_opacity(settings.opacity)
    runtime.set_caption_font_size(settings.caption_font_size)
    runtime.set_always_on_top(settings.always_on_top)
    runtime.set_wander_enabled(
        settings.wander_enabled,
        settings.wander_interval_seconds,
    )

    runtime.set_role_visible("lei", settings.lei_visible)
    runtime.set_role_visible("yu", settings.yu_visible)

    for window in runtime.windows.values():
        window.set_locked(settings.lock_position)
        window.set_click_through(settings.click_through)
        window.set_reduce_motion(settings.reduce_motion)

    from .quiet_hours import in_quiet_hours

    assistant = runtime.assistant
    assistant.configure(
        hourly=settings.hourly_chime,
        break_minutes=settings.break_reminder_minutes,
        focus_minutes=settings.pomodoro_focus_minutes,
        rest_minutes=settings.pomodoro_break_minutes,
    )
    assistant.set_quiet_checker(
        lambda: bool(settings.quiet_hours_enabled)
        and in_quiet_hours(datetime.now(), settings.quiet_start, settings.quiet_end)
    )


def restore_window_positions(runtime, settings) -> None:
    """优先恢复上次位置；没有记录或记录不可用时回到默认排布。"""
    if settings.remember_position:
        saved = {"lei": settings.lei_pos, "yu": settings.yu_pos}
        if runtime.restore_positions(saved):
            return
    runtime.reset_positions_if_needed()


def run_audio_selftest() -> int:
    """检查 QtMultimedia 解码后端是否可用，并试播随包第一段音频。

    这是「没声音」类问题的现场诊断入口：输出 JSON，退出码 0 表示正常。
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    pack_problems: list[str] = []
    pack = resolve_pack(pack_problems)
    if pack is None:
        print(json.dumps({"ok": False, "error": "未找到可用的素材包"}, ensure_ascii=False))
        return 2

    clip = pack.normal_clips[0]
    path = pack.audio_path("normal", clip)
    player = QMediaPlayer()
    output = QAudioOutput()
    player.setAudioOutput(output)
    errors: list[str] = []
    player.errorOccurred.connect(
        lambda error, message: errors.append(message or str(error))
    )
    player.setSource(QUrl.fromLocalFile(str(path)))
    player.play()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        app.processEvents()
        if player.duration() > 0 or player.position() > 0:
            break
        time.sleep(0.02)

    duration = int(player.duration())
    position = int(player.position())
    result = {
        "ok": duration > 0 or position > 0,
        "version": __version__,
        "clip": clip.id,
        "file": path.name,
        "duration_ms": duration,
        "position_ms": position,
        "state": player.playbackState().name,
        "errors": errors,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    # 打包版是 windowed 程序，没有控制台，stdout 看不到；把结果同时写进数据目录。
    with contextlib.suppress(OSError):
        from . import paths

        paths.log_path().with_name("selftest-audio.json").write_text(payload, encoding="utf-8")
    print(payload)
    player.stop()
    return 0 if result["ok"] else 1


def _log_playback_error(message: str) -> None:
    """把播放失败写进日志，避免无声失败无从排查。"""
    LOGGER.warning("播放失败：%s", message)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 中文输出在英文 Windows 控制台（cp1252）会抛 UnicodeEncodeError。
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    from . import config, logging_setup, paths

    logger = logging_setup.setup_logging(paths.log_path())
    logger.info("启动 leiyu_pet %s（%s）", __version__, "便携版" if paths.is_portable() else "安装版")

    if args.selftest_audio:
        return run_audio_selftest()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    from . import autostart

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

    pack_problems: list[str] = []
    pack = resolve_pack(pack_problems)
    if pack is None:
        from .import_wizard import ImportWizard

        wizard = ImportWizard()
        accepted = wizard.exec() == QDialog.DialogCode.Accepted
        if not accepted or wizard.pack is None:
            single.close()
            return 0
        pack = wizard.pack

    from .hotkeys import HotkeyManager
    from .runtime import PetRuntime
    from .settings_dialog import SettingsDialog
    from .tray import TrayManager
    from .update_check import UpdateChecker

    runtime = PetRuntime(pack, show=True)
    runtime.config = cfg
    apply_config(runtime, cfg)
    restore_window_positions(runtime, cfg)
    runtime.controller.playback_error.connect(_log_playback_error)

    def open_settings() -> None:
        SettingsDialog(runtime, cfg).exec()
        with contextlib.suppress(OSError):
            config.save_config(cfg, paths.config_path())

    runtime.on_open_settings = open_settings

    tray = TrayManager(runtime, cfg, on_open_settings=open_settings, on_quit=app.quit)
    tray.show()
    if pack_problems:
        tray.notify(
            "素材校验失败",
            "；".join(pack_problems)[:200],
            warning=True,
        )
    runtime.controller.playback_error.connect(
        lambda message: tray.notify(
            "播放失败",
            f"{message}\n可用 --selftest-audio 检查音频后端",
            warning=True,
        )
    )
    runtime.controller.notice.connect(
        lambda message: tray.notify("提示", message)
    )

    def show_assistant_notice(message: str) -> None:
        """提醒优先用静音气泡；两只都隐藏时退回托盘气泡。"""
        role = random.choice(("lei", "yu"))
        if not runtime.controller.show_notice(role, message):
            tray.notify("提醒", message)

    runtime.assistant.notice.connect(show_assistant_notice)
    runtime.assistant.pomodoro_changed.connect(
        lambda stage: logger.info("番茄钟状态：%s", stage)
    )
    logging_setup.install_excepthook(
        logger,
        notify=lambda title, message: tray.notify(title, message, warning=True),
    )

    # 配置声明开机自启时确保注册表项存在（可能被安全软件清理）。
    autostart.set_enabled(bool(cfg.autostart))

    hotkeys: HotkeyManager | None = None
    if cfg.hotkeys_enabled:
        hotkeys = HotkeyManager()

        def on_hotkey(action: str) -> None:
            if action == "toggle_visible":
                visible = all(runtime.windows[role].isVisible() for role in ("lei", "yu"))
                for role in ("lei", "yu"):
                    runtime.set_role_visible(role, not visible)
            elif action == "crosstalk":
                if not runtime.controller.start_crosstalk():
                    runtime.show_all()
                    runtime.controller.start_crosstalk()
            elif action == "random_line":
                runtime.controller.play_solo(random.choice(("lei", "yu")))
            elif action == "mute":
                runtime.toggle_mute()
            elif action == "stop":
                runtime.controller.stop_all()

        hotkeys.triggered.connect(on_hotkey)
        if hotkeys.install(app) == 0:
            logger.info("全局热键未注册（可能被占用或当前平台不支持）")

    updater: UpdateChecker | None = None
    if cfg.check_updates:
        updater = UpdateChecker(__version__)
        updater.update_available.connect(
            lambda tag, url: tray.notify(
                f"发现新版本 {tag}",
                f"当前版本 v{__version__}，可在发布页下载：{url}",
            )
        )
        updater.failed.connect(lambda message: logger.info("更新检查未完成：%s", message))
        QTimer.singleShot(4000, updater.check)

    # 重复启动时新进程会向本实例发送 "show"，这里把两只桌宠都带出来。
    single.message_received.connect(lambda _message: runtime.show_all())

    def cleanup() -> None:
        if cfg.remember_position:
            positions = runtime.capture_positions()
            cfg.lei_pos = positions.get("lei", [])
            cfg.yu_pos = positions.get("yu", [])
        if hotkeys is not None:
            hotkeys.uninstall()
        with contextlib.suppress(OSError):
            config.save_config(cfg, paths.config_path())
        runtime.close()
        single.close()
        logger.info("退出")

    app.aboutToQuit.connect(cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
