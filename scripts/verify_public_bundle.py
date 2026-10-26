"""素材门禁：只允许随包分发的 AI 素材，拒绝其它位置的人物与音频。

``assets/default_pack/`` 是唯一被放行的素材目录（头像与配音由项目维护者使用
AI 生成并随包分发）。用户自行导入或散落在别处的人物图与音频一律拦截，
避免把不可分发或私有的素材带进 Git 历史或公开构建物。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 唯一放行的素材目录（相对路径小写比较）。
ALLOWED_ASSET_MARKERS = ("assets/default_pack/",)

FORBIDDEN_NAMES = {"lei.png", "yu.png", "encounter.m4a", "helium-ab.mp3", "preview.png"}
FORBIDDEN_PARTS = {"clips", "clips-helium", "local-assets", "imported"}
FORBIDDEN_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac"}


def normalized(path: Path) -> tuple[str, tuple[str, ...]]:
    text = path.as_posix().lower()
    return text, tuple(part.lower() for part in path.parts)


def forbidden_reason(path: Path, *, bundle: bool) -> str | None:
    text, parts = normalized(path)
    if any(marker in text for marker in ALLOWED_ASSET_MARKERS):
        return None
    name = path.name.lower()
    if name in FORBIDDEN_NAMES:
        return f"禁止公开分发的上游素材文件：{text}"
    if any(part in FORBIDDEN_PARTS for part in parts):
        return f"禁止公开分发的素材目录：{text}"
    if bundle and path.suffix.lower() in FORBIDDEN_AUDIO_SUFFIXES:
        return f"公开构建物不得包含音频：{text}"
    return None


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def bundle_files(root: Path) -> list[Path]:
    return [path.relative_to(root) for path in root.rglob("*") if path.is_file()]


def verify(paths: list[Path], *, bundle: bool) -> list[str]:
    return [reason for path in paths if (reason := forbidden_reason(path, bundle=bundle))]


def _use_utf8_stdout() -> None:
    """英文 Windows 控制台默认 cp1252，无法编码中文提示会直接崩溃，这里强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    _use_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("tracked", "bundle"), default="tracked")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    paths = tracked_files(root) if args.mode == "tracked" else bundle_files(root)
    failures = verify(paths, bundle=args.mode == "bundle")
    if failures:
        print("公开素材门禁未通过：")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"公开素材门禁通过：已检查 {len(paths)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
