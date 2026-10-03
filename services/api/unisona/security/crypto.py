"""Envelope encryption for BYOK secrets.

Each workspace gets a random 256-bit data key, stored encrypted under the master key
(UNISONA_MASTER_KEY). Secrets are AES-256-GCM encrypted with the workspace data key
and bound to `workspace_id|purpose` as associated data, so ciphertext copied into
another workspace's row or field fails to decrypt.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import settings

_dek_cache: dict[str, bytes] = {}


def _master() -> bytes:
    raw = settings.unisona_master_key
    if not raw:
        raise RuntimeError("UNISONA_MASTER_KEY is missing: cannot encrypt or decrypt provider keys.")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("UNISONA_MASTER_KEY must be 32 bytes, base64-encoded.")
    return key


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> str:
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, plaintext, aad)).decode()


def _open(key: bytes, token: str, aad: bytes) -> bytes:
    blob = base64.urlsafe_b64decode(token.encode())
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def new_wrapped_dek(workspace_id: str) -> str:
    return _seal(_master(), os.urandom(32), f"dek|{workspace_id}".encode())


def _dek(workspace_id: str, wrapped: str) -> bytes:
    if workspace_id not in _dek_cache:
        _dek_cache[workspace_id] = _open(_master(), wrapped, f"dek|{workspace_id}".encode())
    return _dek_cache[workspace_id]


def encrypt_json(workspace_id: str, wrapped_dek: str, purpose: str, data: dict[str, Any]) -> str:
    return _seal(_dek(workspace_id, wrapped_dek), json.dumps(data).encode(), f"{workspace_id}|{purpose}".encode())


def decrypt_json(workspace_id: str, wrapped_dek: str, purpose: str, token: str) -> dict[str, Any]:
    return json.loads(_open(_dek(workspace_id, wrapped_dek), token, f"{workspace_id}|{purpose}".encode()))


def mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "•" * len(secret)
    return f"{secret[:4]}••••{secret[-4:]}"
