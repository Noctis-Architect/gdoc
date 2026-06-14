"""Hybrid moderation engine: Layer 1 regex/blacklist + Layer 2 AI."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from ai import AIClassifier, ClassificationResult
from database import Database, GroupConfig
from redis_cache import RedisCache
from rule_matcher import match_direct_ban_rules

logger = logging.getLogger(__name__)


@dataclass
class ModerationDecision:
    flagged: bool
    classification: str
    reason: str
    layer: str
    should_delete: bool
    should_warn: bool
    should_ban: bool


class ModerationEngine:
    """Two-layer moderation pipeline."""

    def __init__(
        self,
        db: Database,
        cache: RedisCache,
        ai: AIClassifier,
    ) -> None:
        self.db = db
        self.cache = cache
        self.ai = ai

    async def get_group_config_cached(self, chat_id: int) -> Optional[GroupConfig]:
        cached = await self.cache.get_group_config(chat_id)
        if cached:
            return GroupConfig(
                chat_id=cached["chat_id"],
                title=cached.get("title", ""),
                is_authorized=cached.get("is_authorized", True),
                moderation_enabled=cached.get("moderation_enabled", True),
                strictness=cached.get("strictness", "medium"),
                action_mode=cached.get("action_mode", "keep_alert"),
                warning_threshold=cached.get("warning_threshold", 3),
                custom_rules=cached.get("custom_rules", ""),
                suspect_rules=cached.get("suspect_rules", ""),
            )
        group = await self.db.get_group(chat_id)
        if group:
            await self.cache.set_group_config(
                chat_id,
                {
                    "chat_id": group.chat_id,
                    "title": group.title,
                    "is_authorized": group.is_authorized,
                    "moderation_enabled": group.moderation_enabled,
                    "strictness": group.strictness,
                    "action_mode": group.action_mode,
                    "warning_threshold": group.warning_threshold,
                    "custom_rules": group.custom_rules,
                    "suspect_rules": group.suspect_rules,
                },
            )
        return group

    async def get_blacklist_cached(self, chat_id: int) -> list[dict[str, Any]]:
        cached = await self.cache.get_blacklist(chat_id)
        if cached is not None:
            return cached
        patterns = await self.db.get_blacklist(chat_id)
        await self.cache.set_blacklist(chat_id, patterns)
        return patterns

    async def check_layer1(
        self,
        chat_id: int,
        message_text: str,
    ) -> Optional[ModerationDecision]:
        if not message_text:
            return None

        patterns = await self.get_blacklist_cached(chat_id)
        lowered = message_text.lower()

        for entry in patterns:
            pattern = entry["pattern"]
            is_regex = bool(entry.get("is_regex"))
            matched = False
            try:
                if is_regex:
                    matched = bool(re.search(pattern, message_text, re.IGNORECASE | re.MULTILINE))
                else:
                    matched = pattern.lower() in lowered
            except re.error as exc:
                logger.warning("Invalid regex %r in group %s: %s", pattern, chat_id, exc)
                continue

            if matched:
                return ModerationDecision(
                    flagged=True,
                    classification="VIOLATION",
                    reason=f"Matched blacklist pattern: {pattern}",
                    layer="regex",
                    should_delete=True,
                    should_warn=True,
                    should_ban=False,
                )
        return None

    def check_ban_rules(
        self,
        group: GroupConfig,
        message_text: str,
    ) -> Optional[ModerationDecision]:
        reason = match_direct_ban_rules(message_text, group.custom_rules)
        if not reason:
            return None

        delete_on_violation = group.action_mode == "delete_flag"
        return ModerationDecision(
            flagged=True,
            classification="VIOLATION",
            reason=reason,
            layer="ban_rules",
            should_delete=delete_on_violation,
            should_warn=False,
            should_ban=True,
        )

    async def check_layer2(
        self,
        group: GroupConfig,
        message_text: str,
    ) -> ModerationDecision:
        result: ClassificationResult = await self.ai.classify(
            message_text,
            group.custom_rules,
            group.suspect_rules,
            group.strictness,
        )

        if result.classification == "SUSPECT":
            ban_reason = match_direct_ban_rules(message_text, group.custom_rules)
            if ban_reason:
                result = ClassificationResult("VIOLATION", ban_reason, result.raw_response)

        flagged = result.classification in ("SUSPECT", "VIOLATION")
        if not flagged:
            return ModerationDecision(
                flagged=False,
                classification=result.classification,
                reason=result.reason,
                layer="ai",
                should_delete=False,
                should_warn=False,
                should_ban=False,
            )

        delete_on_violation = group.action_mode == "delete_flag"
        if result.classification == "VIOLATION":
            should_delete = delete_on_violation
            should_warn = False
            should_ban = True
        else:
            should_delete = delete_on_violation and group.strictness == "high"
            should_warn = group.strictness in ("medium", "high")
            should_ban = False

        return ModerationDecision(
            flagged=True,
            classification=result.classification,
            reason=result.reason,
            layer="ai",
            should_delete=should_delete,
            should_warn=should_warn,
            should_ban=should_ban,
        )

    async def evaluate(
        self,
        chat_id: int,
        message_text: str,
    ) -> tuple[Optional[GroupConfig], ModerationDecision]:
        group = await self.get_group_config_cached(chat_id)
        if not group or not group.is_authorized or not group.moderation_enabled:
            return group, ModerationDecision(
                flagged=False,
                classification="SAFE",
                reason="Moderation disabled or group unauthorized",
                layer="none",
                should_delete=False,
                should_warn=False,
                should_ban=False,
            )

        layer1 = await self.check_layer1(chat_id, message_text)
        if layer1:
            if group.action_mode == "keep_alert":
                layer1.should_delete = False
                layer1.should_warn = False
                layer1.should_ban = False
            return group, layer1

        if not message_text.strip():
            return group, ModerationDecision(
                flagged=False,
                classification="SAFE",
                reason="Non-text message",
                layer="none",
                should_delete=False,
                should_warn=False,
                should_ban=False,
            )

        ban_rules_hit = self.check_ban_rules(group, message_text)
        if ban_rules_hit:
            if group.action_mode == "keep_alert":
                ban_rules_hit.should_delete = False
                ban_rules_hit.should_warn = False
                ban_rules_hit.should_ban = False
            return group, ban_rules_hit

        layer2 = await self.check_layer2(group, message_text)
        if layer2.flagged and group.action_mode == "keep_alert":
            layer2.should_delete = False
            layer2.should_warn = False
            layer2.should_ban = False
        return group, layer2

    async def invalidate_group_cache(self, chat_id: int) -> None:
        await self.cache.invalidate_group_config(chat_id)
