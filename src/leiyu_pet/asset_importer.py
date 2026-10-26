"""把用户有权使用的上游素材导入应用数据目录。"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .manifest import load_asset_pack
from .models import AssetPack

ROOT_FILES = ("lei.png", "yu.png", "clips.json", "clips-helium.json", "pairs.json")
AUDIO_DIRS = ("Clips", "Clips-helium")


class AssetImportError(ValueError):
    pass


def _looks_like_asset_root(path: Path) -> bool:
    return all((path / name).is_file() for name in ROOT_FILES) and all(
        (path / name).is_dir() for name in AUDIO_DIRS
    )


def find_asset_root(source: Path | str) -> Path:
    source = Path(source).resolve()
    direct = (source, source / "Assets", source / "Contents" / "Resources")
    for candidate in direct:
        if _looks_like_asset_root(candidate):
            return candidate
    if source.is_dir():
        for manifest in source.rglob("clips.json"):
            candidate = manifest.parent
            if _looks_like_asset_root(candidate):
                return candidate
    raise AssetImportError(f"未在 {source} 中找到完整的原项目 Assets 素材目录")


def _safe_extract(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                relative = PurePosixPath(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise AssetImportError(f"ZIP 包含不安全路径：{member.filename}")
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise AssetImportError(f"无法读取 ZIP：{archive}") from exc


def _copy_pack(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in ROOT_FILES:
        shutil.copy2(source / name, destination / name)
    for folder in AUDIO_DIRS:
        target = destination / folder
        target.mkdir()
        for item in (source / folder).iterdir():
            if item.is_file() and item.suffix.lower() == ".mp3":
                shutil.copy2(item, target / item.name)


def _write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def active_asset_root(store: Path | str) -> Path | None:
    store = Path(store).resolve()
    pointer = store / "current.json"
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        relative = data["path"]
        if not isinstance(relative, str):
            return None
        candidate = (store / relative).resolve()
        packs = (store / "packs").resolve()
        if candidate == packs or packs not in candidate.parents:
            return None
        if not candidate.is_dir():
            return None
        return candidate
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def import_asset_pack(source: Path | str, store: Path | str) -> AssetPack:
    source_path = Path(source).resolve()
    store_path = Path(store).resolve()
    packs = store_path / "packs"
    packs.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="leiyu-import-") as extraction:
        if source_path.is_file():
            if source_path.suffix.lower() != ".zip":
                raise AssetImportError("素材文件必须是 ZIP，或直接选择 Assets 文件夹")
            extracted = Path(extraction)
            _safe_extract(source_path, extracted)
            asset_root = find_asset_root(extracted)
        else:
            asset_root = find_asset_root(source_path)

        load_asset_pack(asset_root)
        pack_id = uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix=f".{pack_id}-", dir=packs) as staging_name:
            staging = Path(staging_name) / "pack"
            _copy_pack(asset_root, staging)
            load_asset_pack(staging)
            final = packs / pack_id
            staging.rename(final)

        _write_json_atomic(store_path / "current.json", {"path": f"packs/{pack_id}"})
        return load_asset_pack(final)
