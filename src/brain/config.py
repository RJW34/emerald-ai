"""
Brain configuration — model tiers, rate limits, env var loading.

Uses OPENROUTER_API_KEY exclusively (never ANTHROPIC_API_KEY).
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BrainConfig:
    """Configuration for the LLM brain module."""

    enabled: bool = False
    openrouter_api_key: str = ""

    # Model tiers
    strategic_model: str = "anthropic/claude-sonnet-4-6"
    tactical_model: str = "anthropic/claude-haiku-4-5"

    # Rate limits
    max_tokens_per_hour: int = 50000
    max_calls_per_hour: int = 30

    # Cache
    cache_ttl_seconds: int = 300  # 5 minutes

    # Paths
    data_dir: Path = field(default_factory=lambda: Path("data/brain"))

    @classmethod
    def from_env(cls) -> "BrainConfig":
        """Load config from environment variables."""
        enabled = os.environ.get("BRAIN_ENABLED", "0").strip().lower() in {
            "1", "true", "yes", "on",
        }
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

        if enabled and not api_key:
            logger.warning(
                "BRAIN_ENABLED=1 but OPENROUTER_API_KEY not set — brain disabled"
            )
            enabled = False

        return cls(
            enabled=enabled,
            openrouter_api_key=api_key,
            strategic_model=os.environ.get(
                "BRAIN_STRATEGIC_MODEL", "anthropic/claude-sonnet-4-6"
            ),
            tactical_model=os.environ.get(
                "BRAIN_TACTICAL_MODEL", "anthropic/claude-haiku-4-5"
            ),
            max_tokens_per_hour=int(
                os.environ.get("BRAIN_MAX_TOKENS_PER_HOUR", "50000")
            ),
            max_calls_per_hour=int(
                os.environ.get("BRAIN_MAX_CALLS_PER_HOUR", "30")
            ),
            cache_ttl_seconds=int(os.environ.get("BRAIN_CACHE_TTL", "300")),
            data_dir=Path(os.environ.get("BRAIN_DATA_DIR", "data/brain")),
        )
