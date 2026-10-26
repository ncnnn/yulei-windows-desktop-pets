from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from leiyu_pet.asset_importer import (
    AssetImportError,
    active_asset_root,
    find_asset_root,
    import_asset_pack,
)


def test_imports_folder_into_versioned_store(asset_pack_factory, tmp_path: Path) -> None:
    source = asset_pack_factory()
    store = tmp_path / "store"
    pack = import_asset_pack(source, store)
    assert pack.root == active_asset_root(store)
    assert pack.root.parent == store / "packs"
    assert pack.root != source
    assert not (pack.root / "encounter.m4a").exists()


def test_imports_zip_with_assets_subdirectory(asset_pack_factory, tmp_path: Path) -> None:
    source = asset_pack_factory()
    archive = tmp_path / "assets.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                bundle.write(path, Path("bundle/Assets") / path.relative_to(source))
    pack = import_asset_pack(archive, tmp_path / "store")
    assert len(pack.pairs) == 8


def test_failed_import_keeps_previous_active_pack(asset_pack_factory, tmp_path: Path) -> None:
    store = tmp_path / "store"
    import_asset_pack(asset_pack_factory(), store)
    before = active_asset_root(store)
    broken = tmp_path / "broken"
    broken.mkdir()
    with pytest.raises(AssetImportError):
        import_asset_pack(broken, store)
    assert active_asset_root(store) == before


def test_finds_parent_assets_directory(asset_pack_factory, tmp_path: Path) -> None:
    parent = tmp_path / "repo"
    parent.mkdir()
    root = asset_pack_factory(parent=parent)
    root.rename(parent / "Assets")
    assert find_asset_root(parent) == parent / "Assets"
