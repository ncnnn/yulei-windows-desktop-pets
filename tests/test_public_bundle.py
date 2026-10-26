from pathlib import Path

from scripts.verify_public_bundle import forbidden_reason, verify


def test_known_upstream_assets_are_rejected() -> None:
    assert forbidden_reason(Path("Assets/lei.png"), bundle=False)
    assert forbidden_reason(Path("Assets/Clips/lei-01.mp3"), bundle=False)
    assert forbidden_reason(Path("local-assets/yu.png"), bundle=False)


def test_neutral_project_assets_are_allowed() -> None:
    paths = [Path("assets/app.ico"), Path("assets/placeholders/empty.svg")]
    assert verify(paths, bundle=True) == []


def test_public_bundle_rejects_audio_anywhere() -> None:
    assert forbidden_reason(Path("random/sample.mp3"), bundle=True)
