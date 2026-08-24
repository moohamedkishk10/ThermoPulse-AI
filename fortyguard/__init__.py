"""
ThermoPulse AI — FortyGuard Temperature API(R) Async Wrapper

    from fortyguard import FortyGuardClient, FortyGuardConfig, polygon_from_bbox
"""

from .client import ActivityHandle, FortyGuardClient, polygon_from_bbox
from .config import FortyGuardConfig
from .exceptions import (
    FortyGuardActivityFailedError,
    FortyGuardAuthError,
    FortyGuardBadRequestError,
    FortyGuardError,
    FortyGuardRateLimitError,
    FortyGuardServerError,
    FortyGuardTimeoutError,
)

__all__ = [
    "FortyGuardClient",
    "FortyGuardConfig",
    "ActivityHandle",
    "polygon_from_bbox",
    "FortyGuardError",
    "FortyGuardAuthError",
    "FortyGuardBadRequestError",
    "FortyGuardRateLimitError",
    "FortyGuardServerError",
    "FortyGuardActivityFailedError",
    "FortyGuardTimeoutError",
]

__version__ = "0.1.0"