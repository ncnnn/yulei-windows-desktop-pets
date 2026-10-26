from pathlib import Path

from scripts.verify_public_bundle import forbidden_reason, verify


def test_known_upstream_assets_outside_default_pack_are_rejected() -> None:
    assert forbidden_reason(Path("Assets/lei.png"), bundle=False)
    assert forbidden_reason(Path("Assets/Clips/lei-01.mp3"), bundle=False)
    assert forbidden_reason(Path("local-assets/yu.png"), bundle=False)
    assert forbidden_reason(Path("assets/imported/yu.png"), bundle=False)


def test_neutral_project_assets_are_allowed() -> None:
    paths = [Path("assets/app.ico"), Path("assets/placeholders/empty.svg")]
    assert verify(paths, bundle=True) == []


def test_public_bundle_rejects_audio_anywhere() -> None:
    assert forbidden_reason(Path("random/sample.mp3"), bundle=True)


def test_default_pack_is_the_only_sanctioned_asset_tree() -> None:
    allowed = [
        Path("assets/default_pack/lei.png"),
        Path("assets/default_pack/yu.png"),
        Path("assets/default_pack/Clips/lei-01.mp3"),
        Path("assets/default_pack/Clips-helium/yu-08.mp3"),
        Path("leiyu_pet/_internal/assets/default_pack/lei.png"),
    ]
    assert verify(allowed, bundle=False) == []
    assert verify(allowed, bundle=True) == []


def test_assets_resembling_default_pack_but_elsewhere_still_rejected() -> None:
    assert forbidden_reason(Path("assets/backup/lei.png"), bundle=True)
    assert forbidden_reason(Path("assets/default_pack_bak/lei.png"), bundle=True)
