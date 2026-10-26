"""拒绝把未授权人物与音频带入 Git 历史或公开构建物。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

FORBIDDEN_NAMES = {"lei.png", "yu.png", "encounter.m4a", "helium-ab.mp3", "preview.png"}
FORBIDDEN_PARTS = {"clips", "clips-helium", "local-assets", "imported"}
FORBIDDEN_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac"}


def normalized(path: Path) -> tuple[str, tuple[str, ...]]:
    text = path.as_posix().lower()
    return text, tuple(part.lower() for part in path.parts)


def forbidden_reason(path: Path, *, bundle: bool) -> str | None:
    text, parts = normalized(path)
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


def main(argv: list[str] | None = None) -> int:
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
