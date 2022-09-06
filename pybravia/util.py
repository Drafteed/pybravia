"""BraviaTV utils and helpers."""
from __future__ import annotations

import re
from http.cookies import SimpleCookie

REGEXP_COOKIE_EXPIRES = re.compile("(;\\s?expires=(.*)(;|$))", re.IGNORECASE)


def normalize_cookies(cookies: list[str]) -> SimpleCookie:
    """Normalize non RFC-compliant cookies."""
    result: SimpleCookie = SimpleCookie()

    for cookie in cookies:
        result.load(REGEXP_COOKIE_EXPIRES.sub("", cookie))

    return result
