"""
Configuration for the FortyGuard API client.

Reads settings from environment variables (via a .env file in development).
Never hardcode the API key — it is always injected at runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """
    Minimal .env loader (avoids a hard dependency on python-dotenv).
    If python-dotenv is installed, it will be preferred automatically.
    """
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path)
        return
    except ImportError:
        pass

    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass(frozen=True)
class FortyGuardConfig:
    """
    Runtime configuration for FortyGuardClient.

    All values can be overridden via environment variables so the same
    code runs locally, in Streamlit Cloud, and in CI without edits.
    """

    api_key: str = field(default_factory=lambda: os.environ.get("FORTYGUARD_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.environ.get("FORTYGUARD_BASE_URL", "https://api.fortyguard.com/v1")
    )

    # Networking / resilience
    request_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("FORTYGUARD_REQUEST_TIMEOUT", "30"))
    )
    max_retries: int = field(default_factory=lambda: int(os.environ.get("FORTYGUARD_MAX_RETRIES", "3")))
    retry_backoff_base_seconds: float = field(
        default_factory=lambda: float(os.environ.get("FORTYGUARD_RETRY_BACKOFF_BASE", "1.5"))
    )

    # Polling (Check Status)
    poll_interval_seconds: float = field(
        default_factory=lambda: float(os.environ.get("FORTYGUARD_POLL_INTERVAL", "5"))
    )
    poll_max_attempts: int = field(
        default_factory=lambda: int(os.environ.get("FORTYGUARD_POLL_MAX_ATTEMPTS", "120"))
    )
    # 120 attempts * 5s = 10 minutes, matching FortyGuard's documented Heat
    # Intelligence example. Heat Intelligence can legitimately take several
    # minutes, so callers needing a longer ceiling should raise this via env.

    # Rate limiting (client-side throttle; FortyGuard's own limits are undocumented,
    # so this is a conservative default that can be tuned per-endpoint later).
    max_concurrent_requests: int = field(
        default_factory=lambda: int(os.environ.get("FORTYGUARD_MAX_CONCURRENCY", "5"))
    )

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "FORTYGUARD_API_KEY is not set. Add it to a .env file "
                "(FORTYGUARD_API_KEY=your_key_here) or export it in your shell. "
                "Never hardcode it in source files."
            )