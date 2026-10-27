"""原项目素材清单的读取与严格校验。"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any, cast

from .models import AssetPack, Clip, ClipLine, DialoguePair, Role

EXPECTED_IDS = set(range(1, 18))
EXPECTED_PAIR_IDS = set(range(1, 9))
EXPECTED_ROLE_COUNTS = {"lei": 9, "yu": 8}


class AssetValidationError(ValueError):
    def __init__(self, issues: list[str] | tuple[str, ...]):
        self.issues = tuple(issues)
        super().__init__("素材包校验失败：\n- " + "\n- ".join(self.issues))


def _load_json(path: Path, issues: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(f"缺少文件：{path.name}")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        issues.append(f"无法读取 {path.name}：{exc}")
    return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _safe_leaf_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.name != value or candidate.is_absolute() or ".." in candidate.parts:
        return None
    return value


def _parse_lines(raw: Any, clip_label: str, duration: float, issues: list[str]) -> tuple[ClipLine, ...]:
    if not isinstance(raw, list) or not raw:
        issues.append(f"{clip_label} 缺少逐句字幕 lines")
        return ()
    result: list[ClipLine] = []
    previous_start = -1.0
    for index, item in enumerate(raw, start=1):
        label = f"{clip_label} 第 {index} 句"
        if not isinstance(item, dict):
            issues.append(f"{label} 不是对象")
            continue
        start = _finite_number(item.get("start"))
        end = _finite_number(item.get("end"))
        text = item.get("text")
        if start is None or end is None:
            issues.append(f"{label} 的 start/end 必须是有限数字")
            continue
        if not isinstance(text, str) or not text.strip():
            issues.append(f"{label} 文本为空")
            continue
        if start < 0 or end < start:
            issues.append(f"{label} 时间范围无效：{start}..{end}")
            continue
        if end > duration + 0.15:
            issues.append(f"{label} 结束时间 {end} 超过片段时长 {duration}")
            continue
        if start < previous_start:
            issues.append(f"{label} 时间顺序倒置")
            continue
        previous_start = start
        result.append(ClipLine(start, end, text.strip()))
    return tuple(result)


def _parse_clips(raw: Any, source_name: str, issues: list[str]) -> tuple[Clip, ...]:
    if not isinstance(raw, list):
        issues.append(f"{source_name} 顶层必须是数组")
        return ()
    result: list[Clip] = []
    for index, item in enumerate(raw, start=1):
        label = f"{source_name} 第 {index} 项"
        if not isinstance(item, dict):
            issues.append(f"{label} 不是对象")
            continue
        clip_id = item.get("id")
        role = item.get("role")
        text = item.get("text")
        file_name = _safe_leaf_name(item.get("file"))
        duration = _finite_number(item.get("duration"))
        if isinstance(clip_id, bool) or not isinstance(clip_id, int) or clip_id <= 0:
            issues.append(f"{label} id 必须是正整数")
            continue
        if role not in ("lei", "yu"):
            issues.append(f"{label} role 必须是 lei 或 yu")
            continue
        if not isinstance(text, str) or not text.strip():
            issues.append(f"{label} text 为空")
            continue
        if file_name is None or Path(file_name).suffix.lower() != ".mp3":
            issues.append(f"{label} file 必须是安全的 MP3 文件名")
            continue
        if duration is None or duration <= 0:
            issues.append(f"{label} duration 必须是正有限数字")
            continue
        lines = _parse_lines(item.get("lines"), label, duration, issues)
        result.append(
            Clip(
                id=clip_id,
                role=cast(Role, role),
                text=text.strip(),
                file=file_name,
                duration=duration,
                lines=lines,
            )
        )
    return tuple(result)


def _parse_pairs(raw: Any, issues: list[str]) -> tuple[DialoguePair, ...]:
    if not isinstance(raw, list):
        issues.append("pairs.json 顶层必须是数组")
        return ()
    result: list[DialoguePair] = []
    for index, item in enumerate(raw, start=1):
        label = f"pairs.json 第 {index} 项"
        if not isinstance(item, dict):
            issues.append(f"{label} 不是对象")
            continue
        values = (item.get("id"), item.get("lei"), item.get("yu"))
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            issues.append(f"{label} 的 id/lei/yu 必须是整数")
            continue
        result.append(DialoguePair(*values))
    return tuple(result)


def png_has_alpha(path: Path) -> bool:
    """只读取 PNG 结构，避免把素材校验耦合到 Qt 或 Pillow。"""
    try:
        with path.open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            while True:
                length_raw = stream.read(4)
                if len(length_raw) != 4:
                    return False
                length = struct.unpack(">I", length_raw)[0]
                kind = stream.read(4)
                payload = stream.read(length)
                if len(payload) != length or len(stream.read(4)) != 4:
                    return False
                if kind == b"IHDR":
                    if length != 13:
                        return False
                    color_type = payload[9]
                    if color_type in (4, 6):
                        return True
                elif kind == b"tRNS":
                    return True
                elif kind == b"IEND":
                    return False
    except OSError:
        return False


def _validate_clip_set(
    clips: tuple[Clip, ...],
    *,
    source_name: str,
    audio_dir: Path,
    issues: list[str],
) -> None:
    ids = [clip.id for clip in clips]
    if set(ids) != EXPECTED_IDS:
        issues.append(f"{source_name} 片段 ID 必须完整覆盖 1..17，实际为 {sorted(set(ids))}")
    if len(ids) != len(set(ids)):
        issues.append(f"{source_name} 存在重复片段 ID")
    counts = {role: sum(clip.role == role for clip in clips) for role in ("lei", "yu")}
    if counts != EXPECTED_ROLE_COUNTS:
        issues.append(f"{source_name} 角色数量应为 lei=9、yu=8，实际为 {counts}")
    for clip in clips:
        audio = audio_dir / clip.file
        if not audio.is_file() or audio.stat().st_size <= 0:
            issues.append(f"缺少或为空的音频：{audio_dir.name}/{clip.file}")


def load_asset_pack(root: Path | str) -> AssetPack:
    root = Path(root).resolve()
    issues: list[str] = []
    normal = _parse_clips(_load_json(root / "clips.json", issues), "clips.json", issues)
    helium = _parse_clips(
        _load_json(root / "clips-helium.json", issues),
        "clips-helium.json",
        issues,
    )
    pairs = _parse_pairs(_load_json(root / "pairs.json", issues), issues)

    for role in ("lei", "yu"):
        image = root / f"{role}.png"
        if not image.is_file():
            issues.append(f"缺少人物图片：{image.name}")
        elif not png_has_alpha(image):
            issues.append(f"人物图片不是带透明通道的 PNG：{image.name}")

    _validate_clip_set(normal, source_name="clips.json", audio_dir=root / "Clips", issues=issues)
    _validate_clip_set(
        helium,
        source_name="clips-helium.json",
        audio_dir=root / "Clips-helium",
        issues=issues,
    )

    normal_by_id = {clip.id: clip for clip in normal}
    helium_by_id = {clip.id: clip for clip in helium}
    if set(normal_by_id) == EXPECTED_IDS and set(helium_by_id) == EXPECTED_IDS:
        for clip_id in sorted(EXPECTED_IDS):
            left = normal_by_id[clip_id]
            right = helium_by_id[clip_id]
            if (left.role, left.text, left.file) != (right.role, right.text, right.file):
                issues.append(f"片段 {clip_id} 在原声与氦气清单中的角色/文本/文件不一致")

    pair_ids = [pair.id for pair in pairs]
    if set(pair_ids) != EXPECTED_PAIR_IDS or len(pair_ids) != len(set(pair_ids)):
        issues.append("pairs.json 必须包含不重复的 1..8 组问答")
    for pair in pairs:
        lei = normal_by_id.get(pair.lei)
        yu = normal_by_id.get(pair.yu)
        if lei is None or lei.role != "lei":
            issues.append(f"问答 {pair.id} 的 lei={pair.lei} 未引用雷军片段")
        if yu is None or yu.role != "yu":
            issues.append(f"问答 {pair.id} 的 yu={pair.yu} 未引用余承东片段")

    if issues:
        raise AssetValidationError(issues)
    # 不去重：相声剧本自己会区分正剧、副歌与收尾句（见 crosstalk.crosstalk_script），
    # 「总有机会 / 追不上」那几组就是故意留着轮换用的。
    return AssetPack(root, normal, helium, pairs)
