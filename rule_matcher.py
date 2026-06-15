"""Deterministic matching for direct ban rules (examples and quoted phrases)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_EXAMPLE_PREFIX = re.compile(
    r"(?:مثال|نمونه|example|e\.g\.?)\s*[:：\-–]\s*(.+)$",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'[«"]([^»"]{2,})[»"]')
_BULLET_PREFIX = re.compile(r"^[-*•\d.)\]]+\s*")
_KEYWORD_PREFIX = re.compile(r"کلیدواژه\s*[:：]\s*(.+)$", re.IGNORECASE)

# Educational / legitimate security discussion — skip hack ban matching.
_SAFE_HACK_CONTEXT = re.compile(
    r"(?:"
    r"دوره\s*(?:هک|امنیت)|"
    r"آموزش\s*(?:هک|امنیت|سایبر)|"
    r"کلاس\s*(?:هک|امنیت)|"
    r"تدریس\s*(?:هک|امنیت)|"
    r"هک\s*و\s*امنیت|"
    r"امنیت\s*سایب|"
    r"cyber\s*security|"
    r"pen\s*test(?:ing)?|"
    r"یاد\s*(?:مید|میدم|داد|ده)|"
    r"آموزش\s*مید|"
    r"security\s*course"
    r")",
    re.IGNORECASE,
)

# Clear illegal-offer signals paired with hack-related content.
_MALICIOUS_HACK_INTENT = re.compile(
    r"(?:"
    r"هک\s*(?:میکن|میزن|می‌کن|می‌زن)|"
    r"(?:میکن|میزن|میفروش|می‌کن|می‌زن|می‌فروش).{0,20}هک|"
    r"هک\s*(?:اکانت|موبایل|گوشی|اینستا|تلگرام|وای.?فای|wifi|سرور)|"
    r"(?:تومن|تومان|ریال|هزار|میلیون)\s*(?:تومن|تومان|ریال)?|"
    r"قیمت\s*\d|"
    r"\d+\s*(?:تومن|تومان|ریال)|"
    r"brute\s*force|"
    r"sql\s*injection|"
    r"رمز\s*(?:وای.?فای|wifi).{0,15}(?:میگیر|می‌گیر|میگیرم)"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BanMatchResult:
    reason: str
    instant_ban: bool


def _normalize_text(text: str) -> str:
    """Normalize Persian/Arabic variants and whitespace for comparison."""
    normalized = text.strip().lower()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = normalized.replace("ة", "ه")
    normalized = re.sub(r"[\u200c\u200d\u200e\u200f]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def is_educational_hack_context(message_text: str) -> bool:
    """True when the message looks like teaching/security education, not an illegal offer."""
    normalized = _normalize_text(message_text)
    if _SAFE_HACK_CONTEXT.search(normalized):
        return True
    if "امنیت" in normalized and "هک" in normalized and not _MALICIOUS_HACK_INTENT.search(normalized):
        return True
    return False


def has_malicious_hack_intent(message_text: str) -> bool:
    return bool(_MALICIOUS_HACK_INTENT.search(_normalize_text(message_text)))


def _is_strong_ban_match(message_text: str, matched_phrase: str) -> bool:
    """Strong matches warrant instant ban; weak ones only warn."""
    normalized_message = _normalize_text(message_text)
    normalized_phrase = _normalize_text(matched_phrase)

    if is_educational_hack_context(message_text):
        return False

    if has_malicious_hack_intent(message_text):
        return True

    word_count = len(normalized_phrase.split())
    if word_count >= 3:
        return True
    if word_count >= 2 and len(normalized_phrase) >= 10:
        return True

    return False


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
    """Extract explicit multi-word keywords from ban rules (کلیدواژه: ...)."""
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
            normalized = _normalize_text(cleaned)
            if len(normalized) < 4:
                continue
            if len(normalized.split()) < 2 and len(normalized) < 8:
                continue
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(cleaned)

    return keywords


def match_direct_ban_rules(message_text: str, ban_rules: str) -> Optional[BanMatchResult]:
    """
    Match ban rules with tiered enforcement.

    - Strong phrase/intent match → instant ban eligible
    - Weak keyword-only match → warn only (delete + warning)
    - Educational hack/security context → no match
    """
    if not message_text.strip() or not ban_rules.strip():
        return None

    if is_educational_hack_context(message_text):
        return None

    normalized_message = _normalize_text(message_text)

    for target in extract_ban_match_targets(ban_rules):
        normalized_target = _normalize_text(target)
        if normalized_target and normalized_target in normalized_message:
            preview = target if len(target) <= 60 else f"{target[:57]}..."
            reason = f"مطابق قوانین بن مستقیم (مثال: {preview})"
            return BanMatchResult(reason, instant_ban=_is_strong_ban_match(message_text, target))

    for keyword in extract_ban_keywords(ban_rules):
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_message:
            preview = keyword if len(keyword) <= 40 else f"{keyword[:37]}..."
            reason = f"مطابق قوانین بن مستقیم (کلیدواژه: {preview})"
            return BanMatchResult(reason, instant_ban=False)

    return None


def match_rule_examples(
    message_text: str,
    rules_text: str,
    rule_kind: str = "قانون",
) -> Optional[str]:
    """
    Return a reason when the message matches an example/phrase from rules.

    Used for suspect rules (admin review), not direct ban.
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
