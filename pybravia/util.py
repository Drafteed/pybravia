"""BraviaTV utils and helpers."""
import re
from http.cookies import SimpleCookie
from typing import Mapping

REGEXP_COOKIE_EXPIRES = re.compile("(;\\s?expires=(.*)(;|$))", re.IGNORECASE)


def normalize_cookies(cookies: str | Mapping) -> SimpleCookie:
    """Normalize non RFC-compliant cookies."""
    new_cookies: SimpleCookie = SimpleCookie()

    if isinstance(cookies, str):
        new_cookies.load(REGEXP_COOKIE_EXPIRES.sub("", cookies))

    if isinstance(cookies, Mapping):
        for cookie in cookies.values():
            new_cookies.load(REGEXP_COOKIE_EXPIRES.sub("", cookie))

    return new_cookies
