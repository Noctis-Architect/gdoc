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

    async def refresh_ai_key(self) -> None:
        api_key = await self.db.get_ai_api_key()
        self.ai.api_key = api_key
