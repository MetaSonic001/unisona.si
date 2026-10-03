"""Local multilingual embeddings (fastembed / ONNX, CPU, no API key)."""
from __future__ import annotations

import asyncio
import threading

from ..config import settings
from ..log import get_logger

log = get_logger("embed")
_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding

            log.info(f"Loading embedding model {settings.embedding_model} (first run downloads ~220 MB)…")
            _model = TextEmbedding(model_name=settings.embedding_model, cache_dir=str(settings.data_path / "models"))
            log.info("Embedding model ready")
    return _model


def embed_sync(texts: list[str]) -> list[list[float]]:
    model = _load()
    return [v.tolist() for v in model.embed(texts, batch_size=32)]


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(embed_sync, texts)


async def warmup() -> None:
    await asyncio.to_thread(_load)
