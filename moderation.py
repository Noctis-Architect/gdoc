"""Hybrid moderation engine: Layer 1 regex/blacklist + rule templates + Layer 2 AI."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from ai import AIClassifier, ClassificationResult
from database import Database, GroupConfig
from redis_cache import RedisCache
from default_profanity import match_default_profanity
from link_filter import check_link_policy
from rule_templates import (
    build_ban_rules_text,
    build_suspect_rules_text,
    parse_enabled_templates,
)

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
    instant_action: bool = False


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

    @staticmethod
    def _resolve_rules(group: GroupConfig) -> tuple[dict[str, bool], str, str]:
        enabled = parse_enabled_templates(group.enabled_templates)
        ban_text = build_ban_rules_text(enabled, group.custom_rules)
        suspect_text = build_suspect_rules_text(enabled, group.suspect_rules)
        return enabled, ban_text, suspect_text

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
                enabled_templates=cached.get("enabled_templates", ""),
                link_policy=cached.get("link_policy", "allow_all"),
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
                    "enabled_templates": group.enabled_templates,
                    "link_policy": group.link_policy,
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

    async def get_link_domains_cached(self, chat_id: int) -> list[str]:
        cached = await self.cache.get_link_domains(chat_id)
        if cached is not None:
            return cached
        domains = await self.db.get_link_domains(chat_id)
        await self.cache.set_link_domains(chat_id, domains)
        return domains

    async def check_links(
        self,
        chat_id: int,
        group: GroupConfig,
        message_text: str,
        entities: list | None = None,
    ) -> Optional[ModerationDecision]:
        if group.link_policy == "allow_all":
            return None

        domains = await self.get_link_domains_cached(chat_id)
        reason = check_link_policy(group.link_policy, domains, message_text, entities)
        if not reason:
            return None

        return ModerationDecision(
            flagged=True,
            classification="VIOLATION",
            reason=reason,
            layer="link_filter",
            should_delete=True,
            should_warn=True,
            should_ban=False,
        )

    async def check_layer1(
        self,
        chat_id: int,
        message_text: str,
    ) -> Optional[ModerationDecision]:
        if not message_text:
            return None

        builtin_hit = match_default_profanity(message_text)
        if builtin_hit:
            return ModerationDecision(
                flagged=True,
                classification="VIOLATION",
                reason=f"فحش یا کلمه نامناسب: {builtin_hit}",
                layer="regex",
                should_delete=True,
                should_warn=True,
                should_ban=False,
            )

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

    async def check_layer2(
        self,
        group: GroupConfig,
        message_text: str,
        ban_rules_text: str,
        suspect_rules_text: str,
    ) -> ModerationDecision:
        if not ban_rules_text.strip() and not suspect_rules_text.strip():
            return ModerationDecision(
                flagged=False,
                classification="SAFE",
                reason="No rules configured",
                layer="ai",
                should_delete=False,
                should_warn=False,
                should_ban=False,
            )

        result: ClassificationResult = await self.ai.classify(
            message_text,
            ban_rules_text,
            suspect_rules_text,
            group.strictness,
        )

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
            return ModerationDecision(
                flagged=True,
                classification=result.classification,
                reason=result.reason,
                layer="ai",
                should_delete=True,
                should_warn=True,
                should_ban=False,
            )

        should_delete = delete_on_violation and group.strictness == "high"
        should_warn = group.strictness in ("medium", "high") and delete_on_violation
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

    def _apply_keep_alert(self, decision: ModerationDecision) -> ModerationDecision:
        """In keep_alert mode, only SUSPECT goes to admin review."""
        if decision.instant_action:
            return decision
        if decision.classification == "SUSPECT":
            return ModerationDecision(
                flagged=True,
                classification=decision.classification,
                reason=decision.reason,
                layer=decision.layer,
                should_delete=False,
                should_warn=False,
                should_ban=False,
            )
        return decision

    async def evaluate(
        self,
        chat_id: int,
        message_text: str,
        entities: list | None = None,
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

        _, ban_rules_text, suspect_rules_text = self._resolve_rules(group)

        link_hit = await self.check_links(chat_id, group, message_text, entities)
        if link_hit:
            if group.action_mode == "keep_alert":
                return group, self._apply_keep_alert(link_hit)
            return group, link_hit

        layer1 = await self.check_layer1(chat_id, message_text)
        if layer1:
            if group.action_mode == "keep_alert":
                return group, self._apply_keep_alert(layer1)
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

        layer2 = await self.check_layer2(
            group, message_text, ban_rules_text, suspect_rules_text,
        )
        if layer2.flagged and group.action_mode == "keep_alert":
            return group, self._apply_keep_alert(layer2)
        return group, layer2

    async def invalidate_group_cache(self, chat_id: int) -> None:
        await self.cache.invalidate_group_config(chat_id)
        await self.cache.invalidate_link_domains(chat_id)
