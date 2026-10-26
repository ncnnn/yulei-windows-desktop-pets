from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

import pytest

TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAA"
    "C0lEQVQImWNgQAcAABIAAW/6Y7cAAAAASUVORK5CYII="
)


@pytest.fixture
def asset_pack_factory(tmp_path: Path) -> Callable[..., Path]:
    sequence = 0

    def build(*, parent: Path | None = None) -> Path:
        nonlocal sequence
        sequence += 1
        root = (parent or tmp_path) / f"Assets-{sequence}"
        root.mkdir(parents=True)
        (root / "Clips").mkdir()
        (root / "Clips-helium").mkdir()
        (root / "lei.png").write_bytes(TRANSPARENT_PNG)
        (root / "yu.png").write_bytes(TRANSPARENT_PNG)

        role_numbers = {"lei": 0, "yu": 0}
        normal = []
        helium = []
        for clip_id in range(1, 18):
            role = "lei" if clip_id % 2 == 1 else "yu"
            role_numbers[role] += 1
            file_name = f"{role}-{role_numbers[role]:02d}.mp3"
            text = f"{role}-{clip_id}"
            duration = 1.0 + clip_id / 100
            item = {
                "id": clip_id,
                "role": role,
                "text": text,
                "file": file_name,
                "duration": duration,
                "lines": [{"start": 0.0, "end": duration, "text": text}],
            }
            normal.append(item)
            fast = json.loads(json.dumps(item))
            fast["duration"] = duration / 1.5
            fast["lines"][0]["end"] = duration / 1.5
            helium.append(fast)
            (root / "Clips" / file_name).write_bytes(b"ID3-test-normal")
            (root / "Clips-helium" / file_name).write_bytes(b"ID3-test-helium")

        pairs = [{"id": pair_id, "lei": pair_id * 2 - 1, "yu": pair_id * 2} for pair_id in range(1, 9)]
        (root / "clips.json").write_text(json.dumps(normal), encoding="utf-8")
        (root / "clips-helium.json").write_text(json.dumps(helium), encoding="utf-8")
        (root / "pairs.json").write_text(json.dumps(pairs), encoding="utf-8")
        return root

    return build
