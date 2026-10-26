"""从随包头像生成 Windows ``.ico``，不依赖 Pillow（仅用 PySide6）。

用法：``python scripts/make_icons.py [输出路径]``
默认输出 ``packaging/app.ico``，内含多分辨率 PNG 帧。
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _square_frame(image: QImage, size: int) -> QImage:
    """等比缩放后居中放到透明正方形画布，避免被 Windows 拉伸变形。"""
    scaled = image.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


def build_ico(source: Path, destination: Path, sizes: tuple[int, ...] = ICON_SIZES) -> Path:
    base = QImage(str(source))
    if base.isNull():
        raise SystemExit(f"无法读取图片：{source}")

    frames: list[tuple[int, bytes]] = []
    for size in sizes:
        frames.append((size, _png_bytes(_square_frame(base, size))))

    directory = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = bytearray()
    payload = bytearray()
    for size, data in frames:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        payload += data
        offset += len(data)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(directory + bytes(entries) + bytes(payload))
    return destination


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if QGuiApplication.instance() is None:
        QGuiApplication(sys.argv)
    root = Path(__file__).resolve().parents[1]
    source = root / "assets" / "default_pack" / "lei.png"
    destination = Path(args[0]) if args else root / "packaging" / "app.ico"
    out = build_ico(source, destination)
    print(f"已生成图标：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
