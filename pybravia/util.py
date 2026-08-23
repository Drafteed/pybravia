"""Utils and helpers."""

from __future__ import annotations

import re
from http.cookies import SimpleCookie
from typing import Any

REGEXP_COOKIE_EXPIRES = re.compile("(;\\s?expires=(.*)(;|$))", re.IGNORECASE)


def normalize_cookies(cookies: list[str]) -> SimpleCookie:
    """Normalize non RFC-compliant cookies."""
    result: SimpleCookie = SimpleCookie()

    for cookie in cookies:
        result.load(REGEXP_COOKIE_EXPIRES.sub("", cookie))

    return result


def deep_redact(obj: Any, keys: list[str]):
    """Redact keys in nested dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if k in keys else deep_redact(v, keys)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [deep_redact(item, keys) for item in obj]
    else:
        return obj
