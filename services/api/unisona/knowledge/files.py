"""Local file store for uploads and recordings (swap for S3/R2 later)."""
from __future__ import annotations

from pathlib import Path

from ..config import settings


def _dir(ws_id: str, kind: str) -> Path:
    p = settings.data_path / "files" / ws_id / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(ws_id: str, source_id: str, data: bytes) -> Path:
    path = _dir(ws_id, "uploads") / source_id
    path.write_bytes(data)
    return path


def read_upload(ws_id: str, source_id: str) -> bytes:
    return (_dir(ws_id, "uploads") / source_id).read_bytes()


def recording_path(ws_id: str, call_id: str) -> Path:
    return _dir(ws_id, "recordings") / f"{call_id}.wav"
