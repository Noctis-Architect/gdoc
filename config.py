"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    """Central configuration for the gdoc moderator bot."""

    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    SUPER_ADMIN_ID: int = int(os.getenv("SUPER_ADMIN_ID", "0"))
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openai").lower()
    AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4o-mini")

    DB_BACKEND: str = os.getenv("DB_BACKEND", "sqlite").lower()
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'gdoc.db'}")
    POSTGRES_DSN: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://gdoc:gdoc@localhost:5432/gdoc",
    )

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_PREFIX: str = os.getenv("REDIS_PREFIX", "gdoc:")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))

    USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

    AI_CONCURRENCY: int = int(os.getenv("AI_CONCURRENCY", "10"))
    DB_WRITE_CONCURRENCY: int = int(os.getenv("DB_WRITE_CONCURRENCY", "5"))

    NOTIFY_QUEUE_DELAY_SECONDS: float = float(os.getenv("NOTIFY_QUEUE_DELAY_SECONDS", "0.15"))
    NOTIFY_DEDUPE_TTL_SECONDS: int = int(os.getenv("NOTIFY_DEDUPE_TTL_SECONDS", "3600"))
    NOTIFY_CROSS_GROUP_MAX_TARGETS: int = int(os.getenv("NOTIFY_CROSS_GROUP_MAX_TARGETS", "50"))

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    STRICTNESS_LEVELS = ("low", "medium", "high")
    ACTION_MODES = ("delete_flag", "keep_alert")
    CLASSIFICATIONS = ("SAFE", "SUSPECT", "VIOLATION")

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.SUPER_ADMIN_ID:
            missing.append("SUPER_ADMIN_ID")
        if not cls.AI_API_KEY:
            missing.append("AI_API_KEY")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
