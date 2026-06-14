"""Redis caching layer for group configs and warning counts."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from config import Config

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache with graceful degradation when Redis is unavailable."""

    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None
        self._available = False

    async def connect(self) -> None:
        try:
            self._client = redis.from_url(
                Config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._client.ping()
            self._available = True
            logger.info("Connected to Redis at %s", Config.REDIS_URL)
        except Exception as exc:
            self._available = False
            logger.warning("Redis unavailable, running without cache: %s", exc)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    def _key(self, suffix: str) -> str:
        return f"{Config.REDIS_PREFIX}{suffix}"

    async def get_group_config(self, chat_id: int) -> Optional[dict[str, Any]]:
        if not self._available or not self._client:
            return None
        try:
            raw = await self._client.get(self._key(f"group:{chat_id}"))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Redis get_group_config failed: %s", exc)
            return None

    async def set_group_config(self, chat_id: int, data: dict[str, Any]) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.setex(
                self._key(f"group:{chat_id}"),
                Config.CACHE_TTL_SECONDS,
                json.dumps(data),
            )
        except Exception as exc:
            logger.debug("Redis set_group_config failed: %s", exc)

    async def invalidate_group_config(self, chat_id: int) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.delete(self._key(f"group:{chat_id}"))
            await self._client.delete(self._key(f"blacklist:{chat_id}"))
        except Exception as exc:
            logger.debug("Redis invalidate_group_config failed: %s", exc)

    async def get_blacklist(self, chat_id: int) -> Optional[list[dict[str, Any]]]:
        if not self._available or not self._client:
            return None
        try:
            raw = await self._client.get(self._key(f"blacklist:{chat_id}"))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Redis get_blacklist failed: %s", exc)
            return None

    async def set_blacklist(self, chat_id: int, patterns: list[dict[str, Any]]) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.setex(
                self._key(f"blacklist:{chat_id}"),
                Config.CACHE_TTL_SECONDS,
                json.dumps(patterns),
            )
        except Exception as exc:
            logger.debug("Redis set_blacklist failed: %s", exc)

    async def get_warning_count(self, chat_id: int, user_id: int) -> Optional[int]:
        if not self._available or not self._client:
            return None
        try:
            raw = await self._client.get(self._key(f"warn:{chat_id}:{user_id}"))
            return int(raw) if raw is not None else None
        except Exception as exc:
            logger.debug("Redis get_warning_count failed: %s", exc)
            return None

    async def set_warning_count(self, chat_id: int, user_id: int, count: int) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.setex(
                self._key(f"warn:{chat_id}:{user_id}"),
                Config.CACHE_TTL_SECONDS,
                str(count),
            )
        except Exception as exc:
            logger.debug("Redis set_warning_count failed: %s", exc)

    async def invalidate_warning_count(self, chat_id: int, user_id: int) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.delete(self._key(f"warn:{chat_id}:{user_id}"))
        except Exception as exc:
            logger.debug("Redis invalidate_warning_count failed: %s", exc)
