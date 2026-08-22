"""Utils and helpers."""

from __future__ import annotations

import re
from base64 import b64encode
from http.cookies import SimpleCookie
from typing import Any

REGEXP_COOKIE_EXPIRES = re.compile("(;\\s?expires=(.*)(;|$))", re.IGNORECASE)


def basic_auth_header(login: str, password: str) -> str:
    """Return the value of an HTTP Basic ``Authorization`` header.

    ``aiohttp.BasicAuth`` is deprecated and goes away in aiohttp 4.0. Its
    replacement, ``aiohttp.encode_basic_auth()``, needs aiohttp 3.14, which
    aioresponses does not support yet.
    """
    return "Basic " + b64encode(f"{login}:{password}".encode()).decode()


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
