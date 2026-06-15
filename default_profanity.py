"""Built-in profanity blacklist applied to every group (Layer 1)."""

from __future__ import annotations

import re
from typing import Any

# Persian and English profanity — substring match after normalization.
DEFAULT_PROFANITY_KEYWORDS: tuple[str, ...] = (
    # Persian
    "کسشر",
    "کس شرف",
    "کیری",
    "کیر",
    "کونی",
    "کون",
    "جنده",
    "حرومزاده",
    "حروم زاده",
    "مادرجنده",
    "مادر جنده",
    "لاشی",
    "لاشخور",
    "کصخل",
    "گوه",
    "گائید",
    "گایید",
    "گاییدم",
    "گائیدم",
    "ننه‌ات",
    "ننت",
    "مادرت",
    "خارکصه",
    "خار کصه",
    "کصکش",
    "کسکش",
    "کونده",
    "کون ده",
    "پوفیوز",
    "آشغال",
    # English
    "fuck",
    "fucking",
    "motherfucker",
    "shit",
    "bitch",
    "asshole",
    "dickhead",
    "pussy",
    "cunt",
    "bastard",
)

# Extra regex patterns for common obfuscations (Layer 1); AI catches subtler bypasses.
DEFAULT_PROFANITY_REGEX: tuple[str, ...] = (
    r"ک[\s\u200c._\-*]+ی[\s\u200c._\-*]+ر",
    r"ک[\s\u200c._\-*]+و[\s\u200c._\-*]+ن",
    r"ج[\s\u200c._\-*]+ن[\s\u200c._\-*]+د[\s\u200c._\-*]+ه",
    r"f[\W_]*u[\W_]*c[\W_]*k",
    r"s[\W_]*h[\W_]*i[\W_]*t",
    r"b[\W_]*i[\W_]*t[\W_]*c[\W_]*h",
)


def normalize_for_match(text: str) -> str:
    """Normalize Persian/Arabic variants and strip obfuscation spacing."""
    normalized = text.strip().lower()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    normalized = re.sub(r"[\u200c\u200d\u200e\u200f]", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def get_default_blacklist_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for keyword in DEFAULT_PROFANITY_KEYWORDS:
        entries.append({"pattern": keyword, "is_regex": False, "builtin": True})
    for pattern in DEFAULT_PROFANITY_REGEX:
        entries.append({"pattern": pattern, "is_regex": True, "builtin": True})
    return entries


def match_default_profanity(message_text: str) -> str | None:
    """Return matched pattern when text hits the built-in profanity list."""
    if not message_text.strip():
        return None

    compact = normalize_for_match(message_text)

    for keyword in DEFAULT_PROFANITY_KEYWORDS:
        if normalize_for_match(keyword) in compact:
            return keyword

    for pattern in DEFAULT_PROFANITY_REGEX:
        try:
            if re.search(pattern, message_text, re.IGNORECASE | re.MULTILINE):
                return pattern
        except re.error:
            continue

    return None
