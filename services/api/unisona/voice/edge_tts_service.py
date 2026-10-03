"""Pipecat TTS service for free Edge neural voices, with automatic language-matched voices.

Each sentence is checked for its script/language; if the agent configured a voice for
that language (or a sensible default exists) the voice switches mid-call. A caller who
moves from English to Hindi hears a native Hindi voice, not an English voice reading
Devanagari.
"""
from __future__ import annotations

import asyncio
import io
from collections import OrderedDict
from collections.abc import AsyncGenerator

import av
import edge_tts
import numpy as np
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

from ..brain.lang import LOCALE_FOR, detect
from ..log import get_logger
from ..providers.voices import LANG_BY_CODE

log = get_logger("tts")

# Short phrases (greetings, "Are you still there?", fillers) are synthesized once and replayed instantly.
_CACHE: OrderedDict[tuple[str, str, str], tuple[np.ndarray, int]] = OrderedDict()
_PENDING: dict[tuple[str, str, str], asyncio.Task] = {}
_CACHE_MAX = 256
_CACHEABLE_CHARS = 220


def _rate(speed: float) -> str:
    return f"{int(round((speed - 1) * 100)):+d}%"


def _remember(key: tuple[str, str, str], pcm: np.ndarray, rate: int) -> None:
    _CACHE[key] = (pcm, rate)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


async def _synthesize(key: tuple[str, str, str]) -> tuple[np.ndarray, int]:
    voice, rate, text = key
    decoder = av.CodecContext.create("mp3", "r")
    parts, sr = [], 24000
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            pcm, sr = _decode_packets(decoder, chunk["data"])
            parts.append(pcm)
    pcm, sr2 = _decode_packets(decoder, None)
    parts.append(pcm)
    out = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)
    _remember(key, out, sr)
    return out, sr


async def prewarm(voice: str | None, text: str, speed: float = 1.0, cfg: dict | None = None) -> None:
    """Synthesize a phrase ahead of time (e.g. the greeting while WebRTC is still connecting)."""
    if not voice or not text.strip() or len(text) > _CACHEABLE_CHARS:
        return
    cfg = cfg or {}
    auto = bool((cfg.get("languages") or {}).get("auto_detect", True))
    voice = voice_for_text(text, voice, (cfg.get("voice") or {}).get("per_language") or {}, auto)
    key = (voice, _rate(speed), text.strip())
    if key in _CACHE or key in _PENDING:
        return
    task = asyncio.create_task(_synthesize(key))
    _PENDING[key] = task
    try:
        await task
    except Exception as e:
        log.warning(f"Prewarm failed for {voice}: {e}")
    finally:
        _PENDING.pop(key, None)


def _decode_mp3(data: bytes) -> tuple[np.ndarray, int]:
    with av.open(io.BytesIO(data), format="mp3") as container:
        stream = container.streams.audio[0]
        rate = stream.rate or 24000
        chunks = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            if arr.ndim > 1:
                arr = arr.mean(axis=0) if arr.shape[0] <= 2 else arr.reshape(-1)
            if arr.dtype != np.float32:
                arr = arr.astype(np.float32) / (32768.0 if np.issubdtype(arr.dtype, np.integer) else 1.0)
            chunks.append(arr)
    if not chunks:
        return np.zeros(0, dtype=np.int16), rate
    pcm = np.clip(np.concatenate(chunks), -1, 1)
    return (pcm * 32767).astype(np.int16), rate


def _to_int16(frames) -> tuple[np.ndarray, int]:
    chunks, rate = [], 24000
    for frame in frames:
        rate = frame.sample_rate or rate
        arr = frame.to_ndarray()
        if arr.ndim > 1:
            arr = arr.mean(axis=0) if arr.shape[0] <= 2 else arr.reshape(-1)
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32) / (32768.0 if np.issubdtype(arr.dtype, np.integer) else 1.0)
        chunks.append(arr)
    if not chunks:
        return np.zeros(0, dtype=np.int16), rate
    return (np.clip(np.concatenate(chunks), -1, 1) * 32767).astype(np.int16), rate


def _decode_packets(decoder, data: bytes | None) -> tuple[np.ndarray, int]:
    """Feed streamed MP3 bytes to an incremental decoder; None flushes it."""
    frames = []
    if data is None:
        try:
            frames += decoder.decode(None)
        except Exception:
            pass
    else:
        for packet in decoder.parse(data):
            frames += decoder.decode(packet)
    return _to_int16(frames)


def voice_for_text(text: str, default_voice: str, per_language: dict[str, str], auto_switch: bool = True) -> str:
    if not auto_switch:
        return default_voice
    code = detect(text)
    if code in {"en", "hinglish"}:
        locale = LOCALE_FOR.get(code)
        override = per_language.get(locale or "")
        if code == "hinglish" and override:
            return override.split(":", 1)[-1]
        return default_voice
    locale = LOCALE_FOR.get(code)
    if not locale:
        return default_voice
    if default_voice.startswith(locale):
        return default_voice
    override = per_language.get(locale)
    if override and override.startswith("edge:"):
        return override.split(":", 1)[1]
    lang = LANG_BY_CODE.get(locale)
    if lang:
        default_gender = "male" if any(m in default_voice for m in ("Madhur", "Prabhat", "Andrew", "Ryan", "Guy")) else "female"
        return lang[default_gender].split(":", 1)[1]
    return default_voice


class EdgeTTSService(TTSService):
    def __init__(self, *, voice: str, per_language: dict[str, str] | None = None, speed: float = 1.0,
                 auto_language: bool = True, **kwargs):
        from pipecat.services.settings import TTSSettings

        kwargs.setdefault("settings", TTSSettings(model=None, voice=voice, language=None))
        super().__init__(push_start_frame=True, push_stop_frames=True, **kwargs)
        self._voice = voice
        self._per_language = per_language or {}
        self._rate = _rate(speed)
        self._auto = auto_language
        self._resampler = create_stream_resampler()

    def can_generate_metrics(self) -> bool:
        return True

    def set_voice_name(self, voice: str) -> None:
        self._voice = voice

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        if not text.strip():
            return
        voice = voice_for_text(text, self._voice, self._per_language, self._auto)
        key = (voice, self._rate, text.strip())
        try:
            await self.start_tts_usage_metrics(text)
            if key not in _CACHE and key in _PENDING:
                try:
                    await _PENDING[key]  # already being synthesized (prewarm): finishing it beats starting over
                except Exception:
                    pass
            if key in _CACHE:
                pcm, rate = _CACHE[key]
                _CACHE.move_to_end(key)
                await self.stop_ttfb_metrics()
                audio = await self._resampler.resample(pcm.tobytes(), rate, self.sample_rate)
                step = self.sample_rate * 2 // 5  # 200 ms frames
                for i in range(0, len(audio), step):
                    yield TTSAudioRawFrame(audio=audio[i:i + step], sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
                return
            cacheable = len(key[2]) <= _CACHEABLE_CHARS
            collected: list[np.ndarray] = []
            # Decode MP3 as it streams in, so playback starts on Edge's first chunk instead of after the whole sentence.
            decoder = av.CodecContext.create("mp3", "r")
            first = True
            async for chunk in edge_tts.Communicate(text, voice, rate=self._rate).stream():
                if chunk["type"] != "audio":
                    continue
                pcm, rate = _decode_packets(decoder, chunk["data"])
                if pcm.size:
                    if cacheable:
                        collected.append(pcm)
                    if first:
                        await self.stop_ttfb_metrics()
                        first = False
                    audio = await self._resampler.resample(pcm.tobytes(), rate, self.sample_rate)
                    if audio:
                        yield TTSAudioRawFrame(audio=audio, sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
            pcm, rate = _decode_packets(decoder, None)  # flush the decoder's tail
            if cacheable and (collected or pcm.size):
                _remember(key, np.concatenate([*collected, pcm]), rate)
            if pcm.size:
                audio = await self._resampler.resample(pcm.tobytes(), rate, self.sample_rate)
                if audio:
                    yield TTSAudioRawFrame(audio=audio, sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
        except Exception as e:
            log.warning(f"Edge TTS failed for voice {voice}: {e}")
            yield ErrorFrame(error=f"Edge TTS error: {e}")
        finally:
            await self.stop_ttfb_metrics()
