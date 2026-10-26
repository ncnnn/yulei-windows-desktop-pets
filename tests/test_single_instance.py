from __future__ import annotations

import uuid
from pathlib import Path

from leiyu_pet.single_instance import SingleInstance


def test_second_instance_is_rejected_and_logged(qtbot, tmp_path: Path) -> None:
    identity = f"LeiYuTest-{uuid.uuid4().hex}"
    first = SingleInstance(tmp_path, identity=identity)
    second = SingleInstance(tmp_path, identity=identity)
    try:
        assert first.acquire() is True
        with qtbot.waitSignal(first.message_received, timeout=1500) as blocker:
            assert second.acquire() is False
        assert blocker.args == ["show"]
        log = (tmp_path / "pet-instance-gate.log").read_text(encoding="utf-8")
        assert "拒绝第二实例" in log
    finally:
        second.close()
        first.close()
