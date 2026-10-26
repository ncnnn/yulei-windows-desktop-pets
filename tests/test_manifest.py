from __future__ import annotations

import json
from pathlib import Path

import pytest

from leiyu_pet.manifest import AssetValidationError, load_asset_pack


def test_loads_complete_original_contract(asset_pack_factory) -> None:
    pack = load_asset_pack(asset_pack_factory())
    assert len(pack.normal_clips) == 17
    assert len(pack.helium_clips) == 17
    assert len(pack.pairs) == 8
    assert len(pack.clips_for("lei", "normal")) == 8
    assert len(pack.clips_for("lei", "normal", include_explicit=True)) == 9
    assert len(pack.clips_for("yu", "normal")) == 8


def test_rejects_missing_audio(asset_pack_factory) -> None:
    root = asset_pack_factory()
    (root / "Clips" / "lei-01.mp3").unlink()
    with pytest.raises(AssetValidationError, match="缺少或为空的音频"):
        load_asset_pack(root)


def test_rejects_out_of_order_caption(asset_pack_factory) -> None:
    root = asset_pack_factory()
    path = root / "clips.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["lines"] = [
        {"start": 0.5, "end": 0.8, "text": "后"},
        {"start": 0.1, "end": 0.4, "text": "前"},
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssetValidationError, match="时间顺序倒置"):
        load_asset_pack(root)


def test_rejects_nontransparent_png(asset_pack_factory) -> None:
    root: Path = asset_pack_factory()
    (root / "lei.png").write_bytes(b"not-png")
    with pytest.raises(AssetValidationError, match="透明通道"):
        load_asset_pack(root)
