"""
Custom exception hierarchy for the FortyGuard API client.

Keeping these distinct lets calling code (Spatial Engine, LangGraph tools)
catch specific failure modes instead of parsing strings.
"""

from __future__ import annotations

from typing import Any, Optional


class FortyGuardError(Exception):
    """Base exception for all FortyGuard API client errors."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.status_code is not None:
            return f"[{self.status_code}] {self.message}"
        return self.message


class FortyGuardAuthError(FortyGuardError):
    """Raised on 401/403 — invalid or missing api-key."""


class FortyGuardBadRequestError(FortyGuardError):
    """Raised on 400 — invalid payload (e.g. date out of range, bad polygon)."""


class FortyGuardRateLimitError(FortyGuardError):
    """Raised on 429 — caller should back off and retry."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class FortyGuardServerError(FortyGuardError):
    """Raised on 5xx — FortyGuard-side failure, safe to retry with backoff."""


class FortyGuardActivityFailedError(FortyGuardError):
    """Raised when an async activity's terminal status is 'Failed'."""

    def __init__(self, message: str, *, activity_id: str, **kwargs):
        super().__init__(message, **kwargs)
        self.activity_id = activity_id


class FortyGuardTimeoutError(FortyGuardError):
    """Raised when polling exceeds the configured max wait without a terminal status."""

    def __init__(self, message: str, *, activity_id: str, **kwargs):
        super().__init__(message, **kwargs)
        self.activity_id = activity_id