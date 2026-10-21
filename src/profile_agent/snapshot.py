"""快照读写（增量状态）。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import BioInfo, Snapshot


def save_snapshot(path: Path, snap: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(snap), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_snapshot(path: Path) -> Snapshot | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    bio_raw = data.get("bio") or {}
    if not isinstance(bio_raw, dict):
        bio_raw = {}
    try:
        return Snapshot(
            schema=int(data.get("schema") or 1),
            username=str(data.get("username") or ""),
            stats_fingerprint=str(data.get("stats_fingerprint") or ""),
            stats_config_hash=str(data.get("stats_config_hash") or ""),
            totals=data.get("totals") or {},
            repos=data.get("repos") or [],
            bio=BioInfo(
                text=str(bio_raw.get("text") or ""),
                input_hash=str(bio_raw.get("input_hash") or ""),
                generated_at=str(bio_raw.get("generated_at") or ""),
                model=str(bio_raw.get("model") or ""),
                prompt_version=int(bio_raw.get("prompt_version") or 0),
            ),
            generated_at=str(data.get("generated_at") or ""),
        )
    except (TypeError, ValueError):
        return None
