"""AI classification layer using OpenAI-compatible or Gemini APIs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from config import Config

logger = logging.getLogger(__name__)

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openai_compat": "",
}

GLOBAL_SYSTEM_RULES = """
You are a Telegram group moderation classifier for the gdoc (Group Doctor) bot.

DEFAULT STANCE: Messages are SAFE unless there is clear, concrete evidence they
break a rule. Normal conversation, opinions, jokes, questions, links to ordinary
websites, and everyday chat are SAFE. When in doubt, choose SAFE. Do NOT flag a
message just because it is short, off-topic, in another language, or unclear.

GLOBAL NON-NEGOTIABLE RULES (always enforce, cannot be overridden):
- Flag as VIOLATION ONLY when the message clearly promotes, offers, requests, or
  instructs: scams, phishing, financial fraud, credential/account theft, malware,
  carding, or tools to bypass security/illegally access systems.
- General mention of these topics, security education, warnings, or news ABOUT
  them is NOT a violation. Intent to commit/enable the act is required.

CLASSIFICATION PRIORITY (highest to lowest):
1. GROUP BAN RULES — read the FULL message and judge INTENT. VIOLATION only when
   the message clearly offers, sells, requests, promotes, or instructs the banned
   activity. Examples (مثال) in rules illustrate what to catch — they are NOT
   keyword triggers. NEVER flag just because a word appears; context matters
   (education, jokes, warnings, news, questions = SAFE).
2. GLOBAL rules above (same intent-based standard).
3. GROUP SUSPECT RULES — same semantic reading; a clear intent match = SUSPECT.
4. STRICTNESS level — only nudges the SAFE↔SUSPECT boundary for suspect rules.
   It must NEVER turn a SAFE message into a violation and must NEVER downgrade a
   clear ban-rule intent match.

CLASSIFICATION LABELS:
- SAFE: Does not clearly break any rule. This is the default and most common label.
- SUSPECT: Clearly matches a group SUSPECT rule (and not a ban rule).
- VIOLATION: Clearly matches a ban rule or a global rule with real malicious intent.

If no ban rule and no suspect rule clearly applies, the answer is SAFE.

Respond ONLY with valid JSON:
{"classification": "SAFE|SUSPECT|VIOLATION", "reason": "brief explanation"}
"""

STRICTNESS_INSTRUCTIONS = {
    "low": (
        "STRICTNESS: LOW — applies to SUSPECT rules only, NOT ban rules. "
        "Be very lenient: only mark SUSPECT when a suspect rule is clearly and "
        "directly matched. Prefer SAFE whenever intent is unclear or the link to "
        "a rule is weak. Ban-rule matches remain VIOLATION."
    ),
    "medium": (
        "STRICTNESS: MEDIUM — applies to SUSPECT rules only, NOT ban rules. "
        "Mark SUSPECT only when a suspect rule is clearly matched. If a message is "
        "merely borderline, vague, or off-topic, classify it SAFE. "
        "Ban-rule matches remain VIOLATION."
    ),
    "high": (
        "STRICTNESS: HIGH — applies to SUSPECT rules only, NOT ban rules. "
        "You may mark borderline cases as SUSPECT, but ONLY when they plausibly "
        "relate to a configured suspect rule. Unrelated normal chat stays SAFE. "
        "Ban-rule matches remain VIOLATION."
    ),
}


@dataclass
class ClassificationResult:
    classification: str
    reason: str
    raw_response: str = ""


class AIClassifier:
    """Async AI moderation classifier with rate limiting."""

    def __init__(
        self,
        api_key: str = "",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.provider = (provider or Config.AI_PROVIDER).lower()
        self.model = model or Config.AI_MODEL
        self.base_url = (base_url or Config.AI_BASE_URL or self.get_default_base_url(self.provider)).rstrip("/")
        self._semaphore = asyncio.Semaphore(Config.AI_CONCURRENCY)
        self._client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def get_default_base_url(provider: str) -> str:
        return DEFAULT_BASE_URLS.get(provider, DEFAULT_BASE_URLS["openai"])

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def list_models(self) -> tuple[list[str], str]:
        """Fetch available models from the configured provider. Returns (models, error)."""
        if not self.api_key:
            return [], "API key not configured"
        if not self._client:
            await self.start()

        try:
            if self.provider == "gemini":
                return await self._list_gemini_models()
            return await self._list_openai_models()
        except httpx.HTTPStatusError as exc:
            return [], f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        except Exception as exc:
            logger.exception("Failed to list models: %s", exc)
            return [], str(exc)

    async def _list_openai_models(self) -> tuple[list[str], str]:
        assert self._client is not None
        url = f"{self.base_url}/models"
        response = await self._client.get(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        response.raise_for_status()
        data = response.json()
        models = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if model_id and self._is_chat_model(model_id):
                models.append(model_id)
        models.sort()
        return models or [self.model], ""

    async def _list_gemini_models(self) -> tuple[list[str], str]:
        assert self._client is not None
        url = f"{self.base_url}/models?key={self.api_key}"
        response = await self._client.get(url)
        response.raise_for_status()
        data = response.json()
        models = []
        for item in data.get("models", []):
            name = item.get("name", "")
            if name.startswith("models/"):
                name = name[7:]
            methods = item.get("supportedGenerationMethods", [])
            if name and ("generateContent" in methods or not methods):
                models.append(name)
        models.sort()
        return models or [self.model], ""

    @staticmethod
    def _is_chat_model(model_id: str) -> bool:
        skip_prefixes = ("text-embedding", "tts-", "whisper", "dall-e", "davinci", "babbage")
        if any(model_id.startswith(p) for p in skip_prefixes):
            return False
        chat_hints = ("gpt", "o1", "o3", "o4", "claude", "llama", "mistral", "gemini", "chat")
        return any(h in model_id.lower() for h in chat_hints)

    async def classify(
        self,
        message_text: str,
        ban_rules: str,
        suspect_rules: str,
        strictness: str,
    ) -> ClassificationResult:
        if not message_text.strip():
            return ClassificationResult("SAFE", "Empty message")

        if not self.api_key:
            return ClassificationResult("SAFE", "AI not configured")

        strictness = strictness if strictness in STRICTNESS_INSTRUCTIONS else "medium"
        user_prompt = self._build_user_prompt(message_text, ban_rules, suspect_rules, strictness)

        async with self._semaphore:
            for attempt in range(3):
                try:
                    if self.provider == "gemini":
                        result = await self._call_gemini(user_prompt)
                    else:
                        result = await self._call_openai(user_prompt)
                    return result
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning("AI rate limited, retrying in %ss", wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.error("AI HTTP error: %s", exc)
                    return ClassificationResult("SAFE", f"AI error: {exc.response.status_code}")
                except httpx.TimeoutException:
                    logger.warning("AI timeout on attempt %s", attempt + 1)
                    await asyncio.sleep(1)
                except Exception as exc:
                    logger.exception("AI classification failed: %s", exc)
                    return ClassificationResult("SAFE", f"AI unavailable: {exc}")

        return ClassificationResult("SAFE", "AI retries exhausted")

    def _build_user_prompt(
        self,
        message_text: str,
        ban_rules: str,
        suspect_rules: str,
        strictness: str,
    ) -> str:
        ban_block = ban_rules.strip()
        suspect_block = suspect_rules.strip()

        parts = [
            STRICTNESS_INSTRUCTIONS[strictness],
            "",
            "GROUP BAN RULES — HIGHEST PRIORITY (intent match = VIOLATION, never SUSPECT):",
            "Read the whole message and decide if the user is actually doing/offering/",
            "selling/requesting the banned thing. Examples (مثال) show the KIND of violation",
            "— do NOT match on shared words alone. If keywords appear but context is",
            "innocent (discussion, education, denial, joke), classify SAFE.",
            ban_block or "(No ban rules configured — nothing here can cause a VIOLATION.)",
            "",
            "GROUP SUSPECT RULES (intent match = SUSPECT only, unless ban rules also match):",
            "Same semantic standard — shared words without violating intent = SAFE.",
            suspect_block or "(No suspect rules configured — nothing here can cause a SUSPECT.)",
            "",
            "DECISION ORDER: check ban rules first → then suspect rules → else SAFE.",
            "If a ban rule clearly matches: VIOLATION.",
            "Else if a suspect rule clearly matches: SUSPECT.",
            "Else: SAFE (this is the default; most messages are SAFE).",
        ]

        if not ban_block and not suspect_block:
            parts.append("")
            parts.append(
                "NOTE: No group rules are configured. Only the GLOBAL rules apply, "
                "so classify as VIOLATION only for clear scams/fraud/malware/etc. "
                "Everything else is SAFE."
            )

        parts.extend([
            "",
            "MESSAGE TO CLASSIFY:",
            message_text[:3000],
        ])
        return "\n".join(parts)

    async def _call_openai(self, user_prompt: str) -> ClassificationResult:
        assert self._client is not None
        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": GLOBAL_SYSTEM_RULES},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_json_response(content)

    async def _call_gemini(self, user_prompt: str) -> ClassificationResult:
        assert self._client is not None
        model = self.model if self.model.startswith("gemini") else "gemini-1.5-flash"
        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        response = await self._client.post(
            url,
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": GLOBAL_SYSTEM_RULES + "\n\n" + user_prompt},
                        ],
                    },
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_json_response(content)

    @staticmethod
    def _parse_json_response(content: str) -> ClassificationResult:
        try:
            parsed = json.loads(content)
            classification = str(parsed.get("classification", "SAFE")).upper()
            reason = str(parsed.get("reason", "No reason provided"))
            if classification not in Config.CLASSIFICATIONS:
                classification = "SAFE"
            return ClassificationResult(classification, reason, content)
        except json.JSONDecodeError:
            match = re.search(
                r'"classification"\s*:\s*"(SAFE|SUSPECT|VIOLATION)"',
                content,
                re.IGNORECASE,
            )
            if match:
                return ClassificationResult(match.group(1).upper(), content[:200], content)
            return ClassificationResult("SAFE", "Could not parse AI response", content)
