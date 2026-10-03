"""Runtime configuration, loaded from the repository-root .env file.

Every optional integration is represented by a `Feature` so the startup banner can
tell the developer exactly what is enabled and which env key would enable the rest.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
API_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    unisona_env: str = "development"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    api_port: int = 8000

    dev_mode: bool = False
    dev_auth_bypass: bool = False
    dev_token: str = ""

    database_url: str = ""
    db_schema: str = "app"
    unisona_master_key: str = ""

    clerk_secret_key: str = ""
    next_public_clerk_publishable_key: str = ""

    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""
    sarvam_api_key: str = ""
    elevenlabs_api_key: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    chroma_mode: str = "embedded"
    chroma_path: str = "./data/chroma"
    chroma_url: str = "http://localhost:8200"
    data_dir: str = "./data"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    local_stt_enabled: bool = True
    local_stt_model: str = "small"

    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = ""
    public_webhook_url: str = ""

    dodo_payments_api_key: str = ""
    dodo_webhook_secret: str = ""
    dodo_environment: str = "test_mode"

    resend_api_key: str = ""
    alert_from_email: str = ""
    slack_alert_webhook_url: str = ""

    run_worker: bool = True
    worker_concurrency: int = 3

    # ── derived ────────────────────────────────────────────────────────────
    @property
    def is_dev(self) -> bool:
        return self.unisona_env.lower() in {"dev", "development", "local"}

    @property
    def dev_bypass_active(self) -> bool:
        return self.is_dev and self.dev_auth_bypass and bool(self.dev_token)

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url.split("?")[0]

    def resolve_path(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (ROOT_DIR / path).resolve()

    @property
    def data_path(self) -> Path:
        p = self.resolve_path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def clerk_issuer(self) -> str:
        """Derive the Clerk Frontend API URL from the publishable key."""
        import base64

        key = self.next_public_clerk_publishable_key
        if not key:
            return ""
        try:
            encoded = key.split("_", 2)[2]
            padded = encoded + "=" * (-len(encoded) % 4)
            host = base64.b64decode(padded).decode().rstrip("$")
            return f"https://{host}"
        except Exception:
            return ""


@dataclass
class Feature:
    name: str
    enabled: bool
    env: str
    note: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def feature_matrix() -> list[Feature]:
    s = settings
    return [
        Feature("Database (Supabase Postgres)", bool(s.database_url), "DATABASE_URL", "required"),
        Feature("BYOK vault encryption", bool(s.unisona_master_key), "UNISONA_MASTER_KEY", "required"),
        Feature("Clerk auth", bool(s.clerk_secret_key and s.clerk_issuer), "CLERK_SECRET_KEY"),
        Feature("Dev auth bypass (local only)", s.dev_bypass_active, "DEV_AUTH_BYPASS + DEV_TOKEN"),
        Feature("Platform LLM: Groq", bool(s.groq_api_key), "GROQ_API_KEY", "chat, voice, analysis, evals"),
        Feature("Platform STT: Groq Whisper", bool(s.groq_api_key), "GROQ_API_KEY", "multilingual speech-to-text"),
        Feature("Prompt-injection model (Prompt Guard 2)", bool(s.groq_api_key), "GROQ_API_KEY", "heuristics still run without it"),
        Feature("Platform LLM: Gemini", bool(s.gemini_api_key), "GEMINI_API_KEY"),
        Feature("Platform LLM: OpenAI", bool(s.openai_api_key), "OPENAI_API_KEY"),
        Feature("Platform STT/TTS: Deepgram", bool(s.deepgram_api_key), "DEEPGRAM_API_KEY"),
        Feature("Platform TTS: Cartesia", bool(s.cartesia_api_key), "CARTESIA_API_KEY"),
        Feature("Platform STT/TTS: Sarvam (Indic)", bool(s.sarvam_api_key), "SARVAM_API_KEY", "or per workspace in Providers"),
        Feature("Speech-to-speech: Gemini Live", bool(s.gemini_api_key), "GEMINI_API_KEY", "or per workspace (BYOK)"),
        Feature("Google Calendar sync", bool(s.google_oauth_client_id and s.google_oauth_client_secret), "GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET"),
        Feature("Instagram + Messenger + WhatsApp webhooks", bool(s.meta_app_secret and s.meta_webhook_verify_token), "META_APP_SECRET + META_WEBHOOK_VERIFY_TOKEN"),
        Feature("Local STT: faster-whisper", s.local_stt_enabled, "LOCAL_STT_ENABLED", "offline fallback"),
        Feature("Free TTS: Edge neural voices", True, "-", "322 voices, 142 locales, no key"),
        Feature("Local TTS: Kokoro", True, "-", "offline English/Hindi/+ voices"),
        Feature("Telegram bots (polling)", True, "-", "bot token added per workspace"),
        Feature("Phone calls + SMS (Twilio/Exotel/Plivo/Telnyx)", bool(s.public_webhook_url), "PUBLIC_WEBHOOK_URL", "plus per-workspace telephony credentials"),
        Feature("Payments: Dodo", bool(s.dodo_payments_api_key), "DODO_PAYMENTS_API_KEY"),
        Feature("Email alerts: Resend", bool(s.resend_api_key and s.alert_from_email), "RESEND_API_KEY + ALERT_FROM_EMAIL"),
        Feature("Slack alerts", bool(s.slack_alert_webhook_url), "SLACK_ALERT_WEBHOOK_URL"),
    ]
