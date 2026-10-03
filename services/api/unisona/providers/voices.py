"""Voice library: one catalog across free cloud (Edge), local (Kokoro) and BYOK engines.

Voice ids are namespaced `engine:voice`, e.g. `edge:hi-IN-SwaraNeural`, `kokoro:af_heart`,
`groq:hannah`. The catalog is cached to disk after the first Edge listing.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import wave
from pathlib import Path

from ..config import settings
from ..log import get_logger

log = get_logger("voices")

# Languages we actively support end to end (STT via Whisper, LLM, TTS via Edge/Kokoro).
LANGUAGES: list[dict] = [
    {"code": "en-IN", "name": "English (India)", "native": "English", "female": "edge:en-IN-NeerjaExpressiveNeural", "male": "edge:en-IN-PrabhatNeural"},
    {"code": "hi-IN", "name": "Hindi", "native": "हिन्दी", "female": "edge:hi-IN-SwaraNeural", "male": "edge:hi-IN-MadhurNeural"},
    {"code": "hinglish", "name": "Hinglish", "native": "Hinglish", "female": "edge:hi-IN-SwaraNeural", "male": "edge:hi-IN-MadhurNeural"},
    {"code": "ta-IN", "name": "Tamil", "native": "தமிழ்", "female": "edge:ta-IN-PallaviNeural", "male": "edge:ta-IN-ValluvarNeural"},
    {"code": "te-IN", "name": "Telugu", "native": "తెలుగు", "female": "edge:te-IN-ShrutiNeural", "male": "edge:te-IN-MohanNeural"},
    {"code": "bn-IN", "name": "Bengali", "native": "বাংলা", "female": "edge:bn-IN-TanishaaNeural", "male": "edge:bn-IN-BashkarNeural"},
    {"code": "mr-IN", "name": "Marathi", "native": "मराठी", "female": "edge:mr-IN-AarohiNeural", "male": "edge:mr-IN-ManoharNeural"},
    {"code": "gu-IN", "name": "Gujarati", "native": "ગુજરાતી", "female": "edge:gu-IN-DhwaniNeural", "male": "edge:gu-IN-NiranjanNeural"},
    {"code": "kn-IN", "name": "Kannada", "native": "ಕನ್ನಡ", "female": "edge:kn-IN-SapnaNeural", "male": "edge:kn-IN-GaganNeural"},
    {"code": "ml-IN", "name": "Malayalam", "native": "മലയാളം", "female": "edge:ml-IN-SobhanaNeural", "male": "edge:ml-IN-MidhunNeural"},
    {"code": "ur-IN", "name": "Urdu", "native": "اردو", "female": "edge:ur-IN-GulNeural", "male": "edge:ur-IN-SalmanNeural"},
    {"code": "en-US", "name": "English (US)", "native": "English", "female": "edge:en-US-AvaMultilingualNeural", "male": "edge:en-US-AndrewMultilingualNeural"},
    {"code": "en-GB", "name": "English (UK)", "native": "English", "female": "edge:en-GB-SoniaNeural", "male": "edge:en-GB-RyanNeural"},
    {"code": "es-ES", "name": "Spanish", "native": "Español", "female": "edge:es-ES-ElviraNeural", "male": "edge:es-ES-AlvaroNeural"},
    {"code": "fr-FR", "name": "French", "native": "Français", "female": "edge:fr-FR-DeniseNeural", "male": "edge:fr-FR-HenriNeural"},
    {"code": "de-DE", "name": "German", "native": "Deutsch", "female": "edge:de-DE-KatjaNeural", "male": "edge:de-DE-ConradNeural"},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "native": "Português", "female": "edge:pt-BR-FranciscaNeural", "male": "edge:pt-BR-AntonioNeural"},
    {"code": "ar-SA", "name": "Arabic", "native": "العربية", "female": "edge:ar-SA-ZariyahNeural", "male": "edge:ar-SA-HamedNeural"},
    {"code": "id-ID", "name": "Indonesian", "native": "Bahasa Indonesia", "female": "edge:id-ID-GadisNeural", "male": "edge:id-ID-ArdiNeural"},
    {"code": "ja-JP", "name": "Japanese", "native": "日本語", "female": "edge:ja-JP-NanamiNeural", "male": "edge:ja-JP-KeitaNeural"},
    {"code": "zh-CN", "name": "Chinese (Mandarin)", "native": "中文", "female": "edge:zh-CN-XiaoxiaoNeural", "male": "edge:zh-CN-YunxiNeural"},
    {"code": "it-IT", "name": "Italian", "native": "Italiano", "female": "edge:it-IT-ElsaNeural", "male": "edge:it-IT-DiegoNeural"},
    {"code": "ru-RU", "name": "Russian", "native": "Русский", "female": "edge:ru-RU-SvetlanaNeural", "male": "edge:ru-RU-DmitryNeural"},
    {"code": "tr-TR", "name": "Turkish", "native": "Türkçe", "female": "edge:tr-TR-EmelNeural", "male": "edge:tr-TR-AhmetNeural"},
    {"code": "ne-NP", "name": "Nepali", "native": "नेपाली", "female": "edge:ne-NP-HemkalaNeural", "male": "edge:ne-NP-SagarNeural"},
]
LANG_BY_CODE = {lang["code"]: lang for lang in LANGUAGES}

KOKORO_VOICES = [
    ("af_heart", "Heart", "female", "en-US"), ("af_bella", "Bella", "female", "en-US"), ("af_nicole", "Nicole", "female", "en-US"),
    ("af_sarah", "Sarah", "female", "en-US"), ("af_sky", "Sky", "female", "en-US"), ("af_nova", "Nova", "female", "en-US"),
    ("af_jessica", "Jessica", "female", "en-US"), ("af_river", "River", "female", "en-US"), ("af_kore", "Kore", "female", "en-US"),
    ("am_adam", "Adam", "male", "en-US"), ("am_michael", "Michael", "male", "en-US"), ("am_eric", "Eric", "male", "en-US"),
    ("am_liam", "Liam", "male", "en-US"), ("am_onyx", "Onyx", "male", "en-US"), ("am_puck", "Puck", "male", "en-US"),
    ("bf_emma", "Emma", "female", "en-GB"), ("bf_isabella", "Isabella", "female", "en-GB"), ("bf_alice", "Alice", "female", "en-GB"),
    ("bm_george", "George", "male", "en-GB"), ("bm_lewis", "Lewis", "male", "en-GB"), ("bm_daniel", "Daniel", "male", "en-GB"),
    ("hf_alpha", "Ananya", "female", "hi-IN"), ("hf_beta", "Diya", "female", "hi-IN"), ("hm_omega", "Arjun", "male", "hi-IN"),
    ("hm_psi", "Rohan", "male", "hi-IN"), ("ef_dora", "Dora", "female", "es-ES"), ("em_alex", "Alex", "male", "es-ES"),
    ("ff_siwis", "Siwis", "female", "fr-FR"), ("if_sara", "Sara", "female", "it-IT"), ("im_nicola", "Nicola", "male", "it-IT"),
    ("pf_dora", "Dora", "female", "pt-BR"), ("pm_alex", "Alex", "male", "pt-BR"), ("jf_alpha", "Hana", "female", "ja-JP"),
    ("zf_xiaobei", "Xiaobei", "female", "zh-CN"), ("zm_yunxi", "Yunxi", "male", "zh-CN"),
]
GROQ_VOICES = [("autumn", "female"), ("diana", "female"), ("hannah", "female"), ("austin", "male"), ("daniel", "male"), ("troy", "male")]

SAMPLE_TEXT = {
    "en": "Hi! I'm your AI assistant. How can I help you today?",
    "hi": "नमस्ते! मैं आपकी AI सहायक हूँ। आज मैं आपकी कैसे मदद कर सकती हूँ?",
    "ta": "வணக்கம்! நான் உங்கள் AI உதவியாளர். இன்று நான் உங்களுக்கு எப்படி உதவலாம்?",
    "te": "నమస్కారం! నేను మీ AI సహాయకురాలిని. ఈ రోజు నేను మీకు ఎలా సహాయం చేయగలను?",
    "bn": "নমস্কার! আমি আপনার AI সহকারী। আজ আমি কীভাবে আপনাকে সাহায্য করতে পারি?",
    "mr": "नमस्कार! मी तुमची AI सहाय्यक आहे. आज मी तुम्हाला कशी मदत करू शकते?",
    "gu": "નમસ્તે! હું તમારી AI સહાયક છું. આજે હું તમને કેવી રીતે મદદ કરી શકું?",
    "kn": "ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ AI ಸಹಾಯಕಿ. ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "ml": "നമസ്കാരം! ഞാൻ നിങ്ങളുടെ AI സഹായിയാണ്. ഇന്ന് ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കും?",
    "ur": "السلام علیکم! میں آپ کی AI معاون ہوں۔ آج میں آپ کی کیسے مدد کر سکتی ہوں؟",
    "es": "¡Hola! Soy tu asistente de IA. ¿Cómo puedo ayudarte hoy?",
    "fr": "Bonjour ! Je suis votre assistante IA. Comment puis-je vous aider ?",
    "de": "Hallo! Ich bin Ihre KI-Assistentin. Wie kann ich Ihnen helfen?",
    "pt": "Olá! Sou sua assistente de IA. Como posso ajudar você hoje?",
    "ar": "مرحباً! أنا مساعدتك الذكية. كيف يمكنني مساعدتك اليوم؟",
    "ja": "こんにちは！AIアシスタントです。今日はどのようにお手伝いできますか？",
    "zh": "你好！我是你的AI助手。今天我能帮你什么？",
    "it": "Ciao! Sono la tua assistente IA. Come posso aiutarti oggi?",
    "id": "Halo! Saya asisten AI Anda. Ada yang bisa saya bantu hari ini?",
    "ru": "Здравствуйте! Я ваш AI-ассистент. Чем могу помочь?",
    "tr": "Merhaba! Ben yapay zeka asistanınızım. Size nasıl yardımcı olabilirim?",
    "ne": "नमस्ते! म तपाईंको AI सहायक हुँ। आज म तपाईंलाई कसरी मद्दत गर्न सक्छु?",
}

_catalog: list[dict] | None = None


def _cache_dir() -> Path:
    p = settings.data_path / "voices"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def catalog() -> list[dict]:
    global _catalog
    if _catalog is not None:
        return _catalog
    cache = _cache_dir() / "edge_voices.json"
    edge: list[dict] = []
    if cache.exists():
        edge = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            import edge_tts

            edge = await edge_tts.list_voices()
            cache.write_text(json.dumps(edge), encoding="utf-8")
        except Exception as e:
            log.warning(f"Edge voice list unavailable ({e}); using built-in defaults only.")
    voices: list[dict] = []
    for v in edge:
        tags = v.get("VoiceTag", {}) or {}
        voices.append({
            "id": f"edge:{v['ShortName']}", "engine": "edge", "name": v.get("FriendlyName", v["ShortName"]).split(" - ")[0].replace("Microsoft ", "").replace(" Online (Natural)", ""),
            "locale": v["Locale"], "gender": v.get("Gender", "").lower(),
            "multilingual": "Multilingual" in v["ShortName"], "styles": tags.get("VoicePersonalities", []),
            "free": True, "local": False,
        })
    for vid, name, gender, locale in KOKORO_VOICES:
        voices.append({"id": f"kokoro:{vid}", "engine": "kokoro", "name": name, "locale": locale, "gender": gender,
                       "multilingual": False, "styles": ["natural"], "free": True, "local": True})
    for vid, gender in GROQ_VOICES:
        voices.append({"id": f"groq:{vid}", "engine": "groq", "name": vid.title(), "locale": "en-US", "gender": gender,
                       "multilingual": False, "styles": ["expressive"], "free": False, "local": False})
    _catalog = voices
    log.info(f"Voice catalog ready: {len(voices)} voices")
    return voices


def sample_text(locale: str) -> str:
    return SAMPLE_TEXT.get(locale.split("-")[0].lower(), SAMPLE_TEXT["en"])


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


_kokoro = None
_kokoro_lock = asyncio.Lock()


async def get_kokoro():
    global _kokoro
    async with _kokoro_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            from pipecat.services.kokoro.tts import KOKORO_CACHE_DIR, _ensure_model_files

            model, voices = KOKORO_CACHE_DIR / "kokoro-v1.0.onnx", KOKORO_CACHE_DIR / "voices-v1.0.bin"
            await asyncio.to_thread(_ensure_model_files, model, voices)
            _kokoro = await asyncio.to_thread(Kokoro, str(model), str(voices))
    return _kokoro


KOKORO_LANG = {"en-US": "en-us", "en-GB": "en-gb", "hi-IN": "hi", "es-ES": "es", "fr-FR": "fr-fr", "it-IT": "it",
               "pt-BR": "pt-br", "ja-JP": "ja", "zh-CN": "cmn"}


async def synthesize(voice_id: str, text: str, groq_key: str | None = None, speed: float = 1.0) -> tuple[bytes, str]:
    """Synthesize a short clip. Returns (audio_bytes, mime)."""
    engine, _, name = voice_id.partition(":")
    if engine == "edge":
        import edge_tts

        rate = f"{int(round((speed - 1) * 100)):+d}%"
        comm = edge_tts.Communicate(text, name, rate=rate)
        audio = bytearray()
        async for ch in comm.stream():
            if ch["type"] == "audio":
                audio.extend(ch["data"])
        return bytes(audio), "audio/mpeg"
    if engine == "kokoro":
        import numpy as np

        kok = await get_kokoro()
        locale = next((v[3] for v in KOKORO_VOICES if v[0] == name), "en-US")
        samples, sr = await asyncio.to_thread(kok.create, text, voice=name, speed=speed, lang=KOKORO_LANG.get(locale, "en-us"))
        return _pcm_to_wav((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes(), sr), "audio/wav"
    if engine == "groq":
        if not groq_key:
            raise RuntimeError("Groq voices need a Groq API key.")
        import httpx

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.groq.com/openai/v1/audio/speech", headers={"Authorization": f"Bearer {groq_key}"},
                             json={"model": "canopylabs/orpheus-v1-english", "voice": name, "input": text[:200], "response_format": "wav"})
            r.raise_for_status()
            return r.content, "audio/wav"
    raise ValueError(f"Unsupported voice engine '{engine}'")


async def preview(voice_id: str, locale: str | None = None, groq_key: str | None = None) -> tuple[Path, str]:
    text = sample_text(locale or "en")
    ext = "mp3" if voice_id.startswith("edge:") else "wav"
    key = hashlib.sha1(f"{voice_id}|{text}".encode()).hexdigest()[:16]
    path = _cache_dir() / f"preview_{key}.{ext}"
    if not path.exists():
        audio, _ = await synthesize(voice_id, text, groq_key=groq_key)
        path.write_bytes(audio)
    return path, "audio/mpeg" if ext == "mp3" else "audio/wav"
