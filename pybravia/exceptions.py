"""BraviaTV exceptions."""


class BraviaTVError(Exception):
    """Base BraviaTV exception."""


class BraviaTVAuthError(BraviaTVError):
    """Raised to indicate auth error."""


class BraviaTVNotFound(BraviaTVError):
    """Raised to indicate not found error."""


class BraviaTVNotSupported(BraviaTVError):
    """Raised to indicate not supported error."""


class BraviaTVConnectionError(BraviaTVError):
    """Raised to indicate connection error."""


class BraviaTVConnectionTimeout(BraviaTVError):
    """Raised to indicate connection timeout."""


class BraviaTVTurnedOff(BraviaTVError):
    """Raised to indicate TV is turned off and do not respond."""
