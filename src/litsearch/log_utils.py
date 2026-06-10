"""Logging setup and secret masking helpers."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SECRET_MASK = "***"
SECRET_KEY_PATTERNS = ("api_key", "apikey", "authorization", "bearer", "token", "secret")


def configure_logging(settings: Any) -> None:
    """Configure root logging from settings."""

    level_name = str(getattr(settings, "log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


def mask_secret(value: Any) -> Any:
    """Mask secret-like values and credentials embedded in URLs."""

    if value is None or value == "":
        return value
    if not isinstance(value, str):
        return value

    masked = re.sub(
        r"(?i)\b(authorization|api[_-]?key|bearer|token|secret)\b\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}={SECRET_MASK}",
        value,
    )
    masked = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", f"Bearer {SECRET_MASK}", masked)

    split = urlsplit(masked)
    if split.scheme and split.netloc and "@" in split.netloc:
        userinfo, hostinfo = split.netloc.rsplit("@", 1)
        if ":" in userinfo:
            username, _password = userinfo.split(":", 1)
            netloc = f"{username}:{SECRET_MASK}@{hostinfo}"
            return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))

    return masked


def mask_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a mapping with secret-looking values masked."""

    safe: dict[str, Any] = {}
    for key, value in mapping.items():
        key_lower = key.lower()
        if isinstance(value, Mapping):
            safe[key] = mask_mapping(value)
        elif any(pattern in key_lower for pattern in SECRET_KEY_PATTERNS):
            safe[key] = SECRET_MASK if value else value
        else:
            safe[key] = mask_secret(value)
    return safe
