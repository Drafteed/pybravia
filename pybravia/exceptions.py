"""BraviaTV exceptions."""


class BraviaTVError(Exception):
    """Base BraviaTV exception."""


class BraviaTVConnectionError(BraviaTVError):
    """Raised to indicate connection error."""


class BraviaTVConnectionTimeout(BraviaTVError):
    """Raised to indicate connection timeout."""
