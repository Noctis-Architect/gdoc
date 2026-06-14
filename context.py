"""Shared application context for handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ai import AIClassifier
from database import Database
from moderation import ModerationEngine
from notification_queue import NotificationQueue
from redis_cache import RedisCache


@dataclass
class BotContext:
    db: Database
    cache: RedisCache
    moderation: ModerationEngine
    ai: AIClassifier
    notify_queue: NotificationQueue
    pending_inputs: dict[int, dict] = field(default_factory=dict)
    model_cache: dict[int, list[str]] = field(default_factory=dict)

    async def refresh_ai_config(self) -> None:
        settings = await self.db.get_ai_settings()
        self.ai.api_key = settings["api_key"]
        self.ai.provider = settings["provider"]
        self.ai.model = settings["model"]
        base_url = settings["base_url"] or AIClassifier.get_default_base_url(settings["provider"])
        self.ai.base_url = base_url.rstrip("/")

    async def refresh_ai_key(self) -> None:
        await self.refresh_ai_config()
