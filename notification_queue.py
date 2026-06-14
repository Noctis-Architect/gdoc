"""Background notification queue with rate limiting for Telegram outbound messages."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TimedOut

from config import Config

logger = logging.getLogger(__name__)


@dataclass(order=True)
class QueuedNotification:
    priority: int
    chat_id: int = field(compare=False)
    text: str = field(compare=False)
    parse_mode: str = field(default="Markdown", compare=False)
    dedupe_key: str = field(default="", compare=False)


class NotificationQueue:
    """Async worker queue that sends Telegram messages with spacing to avoid flood limits."""

    def __init__(
        self,
        bot: Bot,
        delay_seconds: float | None = None,
        max_queue_size: int = 10000,
    ) -> None:
        self._bot = bot
        self._delay = delay_seconds if delay_seconds is not None else Config.NOTIFY_QUEUE_DELAY_SECONDS
        self._max_queue_size = max_queue_size
        self._queue: asyncio.PriorityQueue[QueuedNotification] = asyncio.PriorityQueue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._recent_keys: dict[str, float] = {}
        self._dedupe_ttl = Config.NOTIFY_DEDUPE_TTL_SECONDS

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="gdoc-notify-worker")
        logger.info(
            "Notification queue started (delay=%.2fs, dedupe_ttl=%ss)",
            self._delay,
            self._dedupe_ttl,
        )

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            await self._queue.put(
                QueuedNotification(priority=9999, chat_id=0, text="", dedupe_key="__stop__"),
            )
            try:
                await asyncio.wait_for(self._worker_task, timeout=30.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
            self._worker_task = None
        logger.info("Notification queue stopped")

    async def enqueue(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "Markdown",
        *,
        priority: int = 5,
        dedupe_key: str = "",
    ) -> bool:
        if not self._running:
            logger.warning("Notification queue not running; dropping message to %s", chat_id)
            return False

        if self._queue.qsize() >= self._max_queue_size:
            logger.warning("Notification queue full; dropping message to %s", chat_id)
            return False

        key = dedupe_key or f"{chat_id}:{hash(text)}"
        if self._is_duplicate(key):
            logger.debug("Deduped notification %s", key)
            return False

        await self._queue.put(
            QueuedNotification(
                priority=priority,
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                dedupe_key=key,
            ),
        )
        return True

    async def enqueue_many(
        self,
        items: list[tuple[int, str]],
        *,
        priority: int = 5,
        dedupe_prefix: str = "",
    ) -> int:
        enqueued = 0
        for chat_id, text in items:
            key = f"{dedupe_prefix}:{chat_id}:{hash(text)}" if dedupe_prefix else ""
            if await self.enqueue(chat_id, text, priority=priority, dedupe_key=key):
                enqueued += 1
        return enqueued

    def _is_duplicate(self, key: str) -> bool:
        if not key or key == "__stop__":
            return False
        now = time.monotonic()
        expired = [k for k, ts in self._recent_keys.items() if now - ts > self._dedupe_ttl]
        for k in expired:
            del self._recent_keys[k]
        if key in self._recent_keys:
            return True
        self._recent_keys[key] = now
        return False

    async def _worker(self) -> None:
        while self._running:
            item = await self._queue.get()
            try:
                if item.dedupe_key == "__stop__":
                    break
                if not item.text or not item.chat_id:
                    continue

                sent = await self._send_with_retry(item)
                if sent:
                    await asyncio.sleep(self._delay)
            finally:
                self._queue.task_done()

    async def _send_with_retry(self, item: QueuedNotification, max_attempts: int = 3) -> bool:
        for attempt in range(max_attempts):
            try:
                await self._bot.send_message(
                    chat_id=item.chat_id,
                    text=item.text,
                    parse_mode=item.parse_mode,
                )
                return True
            except RetryAfter as exc:
                wait = exc.retry_after + 1
                logger.warning(
                    "Flood wait %ss for chat %s (attempt %s/%s)",
                    wait,
                    item.chat_id,
                    attempt + 1,
                    max_attempts,
                )
                await asyncio.sleep(wait)
            except Forbidden:
                logger.debug("Cannot message chat %s (blocked or no PM)", item.chat_id)
                return False
            except TimedOut:
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error("Failed to send notification to %s: %s", item.chat_id, exc)
                return False
        await self._queue.put(item)
        return False
