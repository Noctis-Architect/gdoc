"""Link extraction and domain policy checks for group moderation."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

LINK_POLICY_ALLOW_ALL = "allow_all"
LINK_POLICY_BLOCK_ALL = "block_all"
LINK_POLICY_BLOCKLIST = "blocklist"
LINK_POLICY_ALLOWLIST = "allowlist"

LINK_POLICIES = (
    LINK_POLICY_ALLOW_ALL,
    LINK_POLICY_BLOCK_ALL,
    LINK_POLICY_BLOCKLIST,
    LINK_POLICY_ALLOWLIST,
)

_URL_IN_TEXT = re.compile(
    r"(?:https?://|www\.)[^\s<>\"{}|\\^`\[\]]+"
    r"|(?:t\.me|telegram\.me)/[^\s]+"
    r"|(?<![@\w])(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE,
)


def normalize_domain(value: str) -> str:
    """Normalize a URL or bare domain to a comparable host (lowercase, no www)."""
    raw = value.strip().lower()
    if not raw:
        return ""

    if "://" not in raw and not raw.startswith("www."):
        if "/" in raw.split("@")[-1]:
            raw = "http://" + raw
        elif re.match(r"^(?:t\.me|telegram\.me)/", raw):
            raw = "https://" + raw
        elif "." in raw and not raw.startswith("@"):
            raw = "http://" + raw

    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path.split("/")[0]
    else:
        host = raw.split("/")[0]

    host = host.split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip(".")


def domain_matches(pattern: str, domain: str) -> bool:
    """True if domain equals pattern or is a subdomain of pattern."""
    pattern_host = normalize_domain(pattern)
    if not pattern_host or not domain:
        return False
    return domain == pattern_host or domain.endswith("." + pattern_host)


def extract_urls_from_text(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_IN_TEXT.finditer(text):
        candidate = match.group(0).rstrip(".,;:!?)")
        if candidate and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def extract_urls_from_entities(text: str, entities: list[Any] | None) -> list[str]:
    if not entities or not text:
        return []

    urls: list[str] = []
    seen: set[str] = set()

    for entity in entities:
        etype = getattr(entity, "type", None)
        if etype is None and isinstance(entity, dict):
            etype = entity.get("type")

        if etype == "url":
            offset = getattr(entity, "offset", None)
            length = getattr(entity, "length", None)
            if offset is None and isinstance(entity, dict):
                offset = entity.get("offset")
                length = entity.get("length")
            if offset is not None and length is not None:
                fragment = text[offset : offset + length]
                if fragment and fragment not in seen:
                    seen.add(fragment)
                    urls.append(fragment)
        elif etype == "text_link":
            url = getattr(entity, "url", None)
            if url is None and isinstance(entity, dict):
                url = entity.get("url")
            if url and url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def extract_urls(text: str, entities: list[Any] | None = None) -> list[str]:
    seen: set[str] = set()
    combined: list[str] = []
    for url in extract_urls_from_entities(text, entities) + extract_urls_from_text(text):
        if url not in seen:
            seen.add(url)
            combined.append(url)
    return combined


def extract_domains(text: str, entities: list[Any] | None = None) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for url in extract_urls(text, entities):
        domain = normalize_domain(url)
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)
    return domains


def check_link_policy(
    policy: str,
    domain_rules: list[str],
    text: str,
    entities: list[Any] | None = None,
) -> Optional[str]:
    """
    Return a violation reason if links are not allowed, else None.
    """
    if policy == LINK_POLICY_ALLOW_ALL:
        return None

    domains = extract_domains(text, entities)
    if not domains:
        return None

    if policy == LINK_POLICY_BLOCK_ALL:
        return "ارسال لینک در این گروه مجاز نیست"

    if policy == LINK_POLICY_BLOCKLIST:
        if not domain_rules:
            return None
        for domain in domains:
            for rule in domain_rules:
                if domain_matches(rule, domain):
                    return f"لینک دامنه «{domain}» در این گروه مجاز نیست"
        return None

    if policy == LINK_POLICY_ALLOWLIST:
        if not domain_rules:
            return "ارسال لینک در این گروه مجاز نیست (لیست سایت‌های مجاز خالی است)"
        for domain in domains:
            allowed = any(domain_matches(rule, domain) for rule in domain_rules)
            if not allowed:
                return f"فقط لینک سایت‌های مجاز قابل ارسال است (دامنه «{domain}» مجاز نیست)"
        return None

    return None
