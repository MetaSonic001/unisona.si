"""Catalog of every provider a workspace can bring its own key for.

`kind` decides how a key is validated and used:
- "openai_compat": any OpenAI-compatible chat API (validated with GET /models).
- "deepgram", "cartesia", "elevenlabs": provider-specific validation endpoints.
- "local": runs on this machine, no key.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    categories: tuple[str, ...]
    kind: str
    base_url: str = ""
    env: str = ""
    docs_url: str = ""
    default_llm: str = ""
    llm_models: tuple[str, ...] = ()
    fast_llm: str = ""
    stt_models: tuple[str, ...] = ()
    needs_key: bool = True
    notes: str = ""
    extra: dict = field(default_factory=dict)


PROVIDERS: dict[str, ProviderSpec] = {p.id: p for p in [
    ProviderSpec("groq", "Groq", ("llm", "stt", "tts"), "openai_compat", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
                 "https://console.groq.com/keys", "openai/gpt-oss-120b",
                 ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"), "qwen/qwen3.8-27b",
                 ("whisper-large-v3-turbo", "whisper-large-v3"), notes="Fastest inference. Free tier available."),
    ProviderSpec("gemini", "Google Gemini", ("llm",), "openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
                 "https://aistudio.google.com/apikey", "gemini-2.5-flash", ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"), "gemini-2.5-flash-lite",
                 notes="Generous free tier."),
    ProviderSpec("openai", "OpenAI", ("llm", "stt", "tts"), "openai_compat", "https://api.openai.com/v1", "OPENAI_API_KEY",
                 "https://platform.openai.com/api-keys", "gpt-4.1-mini", ("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"), "gpt-4.1-mini",
                 ("gpt-4o-mini-transcribe", "whisper-1")),
    ProviderSpec("anthropic", "Anthropic Claude", ("llm",), "openai_compat", "https://api.anthropic.com/v1", "",
                 "https://console.anthropic.com/settings/keys", "claude-sonnet-4-5", ("claude-sonnet-4-5", "claude-haiku-4-5"), "claude-haiku-4-5"),
    ProviderSpec("openrouter", "OpenRouter", ("llm",), "openai_compat", "https://openrouter.ai/api/v1", "",
                 "https://openrouter.ai/keys", "meta-llama/llama-3.3-70b-instruct", ("meta-llama/llama-3.3-70b-instruct", "google/gemini-2.5-flash", "deepseek/deepseek-chat"),
                 notes="One key, hundreds of models."),
    ProviderSpec("cerebras", "Cerebras", ("llm",), "openai_compat", "https://api.cerebras.ai/v1", "",
                 "https://cloud.cerebras.ai", "gpt-oss-120b", ("gpt-oss-120b", "qwen-3-32b")),
    ProviderSpec("mistral", "Mistral", ("llm",), "openai_compat", "https://api.mistral.ai/v1", "",
                 "https://console.mistral.ai/api-keys", "mistral-small-latest", ("mistral-small-latest", "mistral-large-latest")),
    ProviderSpec("deepseek", "DeepSeek", ("llm",), "openai_compat", "https://api.deepseek.com/v1", "",
                 "https://platform.deepseek.com/api_keys", "deepseek-chat", ("deepseek-chat",)),
    ProviderSpec("together", "Together AI", ("llm",), "openai_compat", "https://api.together.xyz/v1", "",
                 "https://api.together.xyz/settings/api-keys", "meta-llama/Llama-3.3-70B-Instruct-Turbo", ("meta-llama/Llama-3.3-70B-Instruct-Turbo",)),
    ProviderSpec("fireworks", "Fireworks", ("llm",), "openai_compat", "https://api.fireworks.ai/inference/v1", "",
                 "https://fireworks.ai/account/api-keys", "accounts/fireworks/models/llama-v3p3-70b-instruct", ("accounts/fireworks/models/llama-v3p3-70b-instruct",)),
    ProviderSpec("custom", "Custom OpenAI-compatible", ("llm",), "openai_compat", "", "",
                 "", "", (), notes="Any OpenAI-compatible endpoint (vLLM, LM Studio, Azure, your own)."),
    ProviderSpec("ollama", "Ollama (local)", ("llm",), "openai_compat", "http://localhost:11434/v1", "",
                 "https://ollama.com", "llama3.2", ("llama3.2", "qwen2.5", "gemma3"), "llama3.2", needs_key=False,
                 notes="Runs models on this machine. Free and private."),
    ProviderSpec("deepgram", "Deepgram", ("stt", "tts"), "deepgram", "https://api.deepgram.com/v1", "DEEPGRAM_API_KEY",
                 "https://console.deepgram.com", stt_models=("nova-3",), notes="Best streaming phone STT. $200 free credit."),
    ProviderSpec("cartesia", "Cartesia", ("tts",), "cartesia", "https://api.cartesia.ai", "CARTESIA_API_KEY",
                 "https://play.cartesia.ai/keys", notes="Ultra-low-latency natural voices."),
    ProviderSpec("elevenlabs", "ElevenLabs", ("tts",), "elevenlabs", "https://api.elevenlabs.io/v1", "ELEVENLABS_API_KEY",
                 "https://elevenlabs.io/app/settings/api-keys", notes="Premium voices (you pay ElevenLabs directly)."),
    ProviderSpec("sarvam", "Sarvam AI", ("stt", "tts"), "sarvam", "https://api.sarvam.ai", "SARVAM_API_KEY",
                 "https://dashboard.sarvam.ai", stt_models=("saaras:v4",),
                 notes="Indian-language specialist: Saaras STT (22 languages, code-mixed) and Bulbul voices. Free credits."),
    ProviderSpec("google_live", "Gemini Live (speech-to-speech)", ("s2s",), "gemini_live", "https://generativelanguage.googleapis.com", "GEMINI_API_KEY",
                 "https://aistudio.google.com/apikey", notes="Native audio model: one model listens and speaks. Smoothest calls; uses your Gemini key."),
    ProviderSpec("razorpay", "Razorpay (your payments)", ("payments",), "razorpay", "https://api.razorpay.com/v1", "",
                 "https://dashboard.razorpay.com/app/keys", notes="Send payment links to your customers (INR/UPI). Key ID + secret."),
    ProviderSpec("stripe", "Stripe (your payments)", ("payments",), "stripe", "https://api.stripe.com/v1", "",
                 "https://dashboard.stripe.com/apikeys", notes="Send payment links to your customers worldwide."),
    ProviderSpec("edge", "Edge neural voices", ("tts",), "local", needs_key=False, notes="322 free neural voices in 142 locales, incl. 10 Indian languages."),
    ProviderSpec("kokoro", "Kokoro (local)", ("tts",), "local", needs_key=False, notes="Natural offline voices, runs on CPU."),
    ProviderSpec("whisper_local", "Whisper (local)", ("stt",), "local", needs_key=False, notes="Offline multilingual STT on CPU."),
]}

# USD per 1M tokens (input, output); rough public prices used only for cost estimates.
LLM_PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.29, 0.59),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-haiku-4-5": (1.0, 5.0),
}
STT_PRICE_PER_MIN = {"groq": 0.0006, "openai": 0.003, "deepgram": 0.0043, "whisper_local": 0.0}
TTS_PRICE_PER_1K_CHARS = {"edge": 0.0, "kokoro": 0.0, "groq": 0.05, "openai": 0.015, "cartesia": 0.05, "elevenlabs": 0.18, "deepgram": 0.015}


def estimate_llm_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = LLM_PRICES.get(model, (0.5, 1.5))
    return round((tokens_in * pin + tokens_out * pout) / 1_000_000, 6)


def public_catalog() -> list[dict]:
    return [
        {
            "id": p.id, "name": p.name, "categories": list(p.categories), "needs_key": p.needs_key,
            "docs_url": p.docs_url, "default_llm": p.default_llm, "llm_models": list(p.llm_models),
            "stt_models": list(p.stt_models), "notes": p.notes, "custom_base_url": p.id in {"custom", "ollama"},
        }
        for p in PROVIDERS.values()
    ]
