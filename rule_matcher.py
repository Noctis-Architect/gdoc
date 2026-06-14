"""Deterministic matching for direct ban rules (examples and quoted phrases)."""

from __future__ import annotations

import re
from typing import Optional

_EXAMPLE_PREFIX = re.compile(
    r"(?:مثال|نمونه|example|e\.g\.?)\s*[:：\-–]\s*(.+)$",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'[«"]([^»"]{2,})[»"]')
_BULLET_PREFIX = re.compile(r"^[-*•\d.)\]]+\s*")
_KEYWORD_PREFIX = re.compile(r"کلیدواژه\s*[:：]\s*(.+)$", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    """Normalize Persian/Arabic variants and whitespace for comparison."""
    normalized = text.strip().lower()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = normalized.replace("ة", "ه")
    normalized = re.sub(r"[\u200c\u200d\u200e\u200f]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def extract_ban_match_targets(rules_text: str) -> list[str]:
    """Extract example phrases and quoted samples from direct ban rules."""
    if not rules_text.strip():
        return []

    targets: list[str] = []
    seen: set[str] = set()

    def add_target(raw: str) -> None:
        cleaned = raw.strip().strip(".,;:!?")
        if len(cleaned) < 2:
            return
        key = _normalize_text(cleaned)
        if key and key not in seen:
            seen.add(key)
            targets.append(cleaned)

    for line in rules_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        example_match = _EXAMPLE_PREFIX.search(stripped)
        if example_match:
            add_target(example_match.group(1))
            continue

        for quoted in _QUOTED.findall(stripped):
            add_target(quoted)

        body = _BULLET_PREFIX.sub("", stripped)
        if body and len(body) <= 120:
            if re.search(r"(?:مثال|نمونه|example)\b", body, re.IGNORECASE):
                continue
            if re.search(r"(?:مانند|مثل)\s*[:：]", body, re.IGNORECASE):
                parts = re.split(r"[:：]", body, maxsplit=1)
                if len(parts) == 2:
                    add_target(parts[1])

    return targets


def extract_ban_keywords(rules_text: str) -> list[str]:
    """Extract explicit keywords from ban rules (کلیدواژه: ...)."""
    if not rules_text.strip():
        return []

    keywords: list[str] = []
    seen: set[str] = set()

    for line in rules_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        keyword_match = _KEYWORD_PREFIX.search(stripped)
        if not keyword_match:
            continue
        for part in re.split(r"[,،]", keyword_match.group(1)):
            cleaned = part.strip().strip(".,;:!?")
            if len(cleaned) < 2:
                continue
            key = _normalize_text(cleaned)
            if key and key not in seen:
                seen.add(key)
                keywords.append(cleaned)

    return keywords


def match_direct_ban_rules(message_text: str, ban_rules: str) -> Optional[str]:
    """Return a violation reason when the message matches ban-rule examples or keywords."""
    if not message_text.strip() or not ban_rules.strip():
        return None

    hit = match_rule_examples(message_text, ban_rules, "بن مستقیم")
    if hit:
        return hit

    normalized_message = _normalize_text(message_text)
    for keyword in extract_ban_keywords(ban_rules):
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_message:
            preview = keyword if len(keyword) <= 40 else f"{keyword[:37]}..."
            return f"مطابق قوانین بن مستقیم (کلیدواژه: {preview})"

    return None


def match_rule_examples(
    message_text: str,
    rules_text: str,
    rule_kind: str = "قانون",
) -> Optional[str]:
    """
    Return a reason when the message matches an example/phrase from rules.

    Runs before AI so explicit examples always produce deterministic matches.
    """
    if not message_text.strip() or not rules_text.strip():
        return None

    normalized_message = _normalize_text(message_text)
    for target in extract_ban_match_targets(rules_text):
        normalized_target = _normalize_text(target)
        if normalized_target and normalized_target in normalized_message:
            preview = target if len(target) <= 60 else f"{target[:57]}..."
            return f"مطابق قوانین {rule_kind} (مثال: {preview})"

    return None
