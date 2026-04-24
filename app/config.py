"""Central config. Loaded once at startup; fails fast if required env vars are missing."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str
    bot_username: str
    webhook_url: str
    webhook_secret_token: str

    # LLM
    openai_api_key: str

    # Voice
    elevenlabs_api_key: str
    aunty_may_voice_id: str

    # Data
    supabase_url: str
    supabase_service_key: str
    supabase_storage_bucket: str = "briefings"
    database_url: str  # direct Postgres "Session" DSN for APScheduler job store

    # Behaviour
    tz: str = "Asia/Singapore"
    confirmation_window_min: int = 15
    check_back_offset_min: int = 12
    pattern_window_days: int = 42
    demo_mode_fast_forward: bool = False
    voice_disabled: bool = False  # dev flag: bot sends text + accepts parent text replies (skip ElevenLabs)
    gp_name_default: str = "Dr Tan"
    sg_emergency_number: str = "995"
    audio_cache_dir: Path = Path("./cache/audio")
    log_level: str = "INFO"

    # Demo seeds (optional; filled in after Telegram group setup)
    demo_family_id: str | None = None
    demo_group_chat_id: int | None = None


settings = Settings()  # type: ignore[call-arg]
