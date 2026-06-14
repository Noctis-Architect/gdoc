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


def match_direct_ban_rules(message_text: str, ban_rules: str) -> Optional[str]:
    """
    Return a violation reason when the message matches a ban-rule example/phrase.

    This runs before AI so explicit ban examples always produce VIOLATION, not SUSPECT.
    """
    if not message_text.strip() or not ban_rules.strip():
        return None

    normalized_message = _normalize_text(message_text)
    for target in extract_ban_match_targets(ban_rules):
        normalized_target = _normalize_text(target)
        if normalized_target and normalized_target in normalized_message:
            preview = target if len(target) <= 60 else f"{target[:57]}..."
            return f"مطابق قوانین بن مستقیم (مثال: {preview})"

    return None
