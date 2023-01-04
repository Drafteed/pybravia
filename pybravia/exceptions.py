"""Bravia exceptions."""


class BraviaError(Exception):
    """Base Bravia exception."""


class BraviaAuthError(BraviaError):
    """Raised to indicate auth error."""


class BraviaNotFound(BraviaError):
    """Raised to indicate not found error."""


class BraviaNotSupported(BraviaError):
    """Raised to indicate not supported error."""


class BraviaConnectionError(BraviaError):
    """Raised to indicate connection error."""


class BraviaConnectionTimeout(BraviaError):
    """Raised to indicate connection timeout."""


class BraviaTurnedOff(BraviaError):
    """Raised to indicate that TV is turned off and do not respond."""
