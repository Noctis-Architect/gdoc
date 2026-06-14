"""Webhook configuration helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path


def normalize_webhook_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith("https://"):
        if url.startswith("http://"):
            url = "https://" + url[7:]
        else:
            url = "https://" + url
    return url


def validate_webhook_url(url: str) -> bool:
    return bool(re.match(r"^https://[a-zA-Z0-9._-]+(\.[a-zA-Z0-9._-]+)+(/.*)?$", url))


def update_env_file(env_path: str, updates: dict[str, str]) -> tuple[bool, str]:
    """Update specific keys in the .env file."""
    path = Path(env_path)
    if not path.exists():
        return False, f".env not found at {env_path}"

    lines = path.read_text().splitlines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        matched = False
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated_keys.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n")
    os.chmod(path, 0o600)
    return True, "Environment file updated"
