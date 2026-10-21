"""File store for uploads and call recordings.

Local disk (`data/files/...`) is always written first and used as a cache. When Supabase credentials are set
(NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SECRET_KEY) every file is also stored in a private Supabase Storage bucket,
so uploads and recordings survive redeploys on hosts with an ephemeral disk (Render, Railway, ...).
Reads fall back to the bucket when the local copy is gone. Storage keys look like `<ws>/<kind>/<name>`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from ..config import settings
from ..log import get_logger

log = get_logger("files")
_bucket_ready = False
_bucket_lock = asyncio.Lock()


def _local(key: str) -> Path:
    p = settings.data_path / "files" / key
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _headers() -> dict[str, str]:
    k = settings.supabase_secret_key
    return {"apikey": k, "Authorization": f"Bearer {k}"}


def _base() -> str:
    return settings.next_public_supabase_url.rstrip("/") + "/storage/v1"


async def _ensure_bucket(client: httpx.AsyncClient) -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    async with _bucket_lock:
        if _bucket_ready:
            return
        r = await client.get(f"{_base()}/bucket/{settings.storage_bucket}", headers=_headers())
        if r.status_code != 200:
            r = await client.post(f"{_base()}/bucket", headers=_headers(),
                                  json={"id": settings.storage_bucket, "name": settings.storage_bucket, "public": False})
            if r.status_code not in (200, 201, 409) and "already exists" not in r.text.lower():
                raise RuntimeError(f"could not create storage bucket: {r.status_code} {r.text[:200]}")
            log.info(f"Created private storage bucket '{settings.storage_bucket}'")
        _bucket_ready = True


async def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    await asyncio.to_thread(_local(key).write_bytes, data)
    if not settings.remote_storage:
        return
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await _ensure_bucket(client)
            r = await client.post(f"{_base()}/object/{settings.storage_bucket}/{key}", content=data,
                                  headers={**_headers(), "content-type": content_type, "x-upsert": "true"})
            r.raise_for_status()
    except Exception as e:
        log.error(f"Remote storage upload failed for {key} (kept on local disk only, lost on redeploy): {e}")


async def get(key: str) -> bytes | None:
    p = _local(key)
    if p.exists():
        return await asyncio.to_thread(p.read_bytes)
    if not settings.remote_storage:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(f"{_base()}/object/{settings.storage_bucket}/{key}", headers=_headers())
            if r.status_code in (400, 404):
                return None
            r.raise_for_status()
            await asyncio.to_thread(p.write_bytes, r.content)
            return r.content
    except Exception as e:
        log.error(f"Remote storage download failed for {key}: {e}")
        return None


async def save_upload(ws_id: str, source_id: str, data: bytes) -> str:
    key = f"{ws_id}/uploads/{source_id}"
    await put(key, data)
    return key


async def read_upload(ws_id: str, source_id: str) -> bytes:
    data = await get(f"{ws_id}/uploads/{source_id}")
    if data is None:
        raise FileNotFoundError("The uploaded file is no longer available. Please upload it again.")
    return data


async def save_recording(ws_id: str, call_id: str, wav: bytes) -> str:
    key = f"{ws_id}/recordings/{call_id}.wav"
    await put(key, wav, "audio/wav")
    return key


async def read_recording(ref: str) -> bytes | None:
    """`ref` is a storage key (new) or an absolute local path (recordings made before remote storage)."""
    p = Path(ref)
    if p.is_absolute():
        return await asyncio.to_thread(p.read_bytes) if p.exists() else None
    return await get(ref)
