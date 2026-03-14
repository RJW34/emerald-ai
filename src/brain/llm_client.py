"""
OpenRouter API wrapper — routes all LLM calls through OpenRouter.

Never touches ANTHROPIC_API_KEY.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .config import BrainConfig

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    latency_ms: float


class TokenBudget:
    """Tracks token usage per hour to enforce budget."""

    def __init__(self, max_tokens_per_hour: int, max_calls_per_hour: int):
        self.max_tokens = max_tokens_per_hour
        self.max_calls = max_calls_per_hour
        self._usage: list[tuple[float, int]] = []  # (timestamp, tokens)

    def can_spend(self, estimated_tokens: int = 1000) -> bool:
        self._prune()
        current_tokens = sum(t for _, t in self._usage)
        current_calls = len(self._usage)
        return (
            current_tokens + estimated_tokens <= self.max_tokens
            and current_calls < self.max_calls
        )

    def record(self, tokens: int):
        self._usage.append((time.time(), tokens))

    def _prune(self):
        cutoff = time.time() - 3600
        self._usage = [(ts, t) for ts, t in self._usage if ts > cutoff]

    def get_usage(self) -> dict:
        self._prune()
        return {
            "tokens_this_hour": sum(t for _, t in self._usage),
            "calls_this_hour": len(self._usage),
            "max_tokens": self.max_tokens,
            "max_calls": self.max_calls,
        }


class OpenRouterClient:
    """Sends chat completion requests to OpenRouter API."""

    def __init__(self, config: BrainConfig):
        self.config = config
        self.budget = TokenBudget(
            config.max_tokens_per_hour, config.max_calls_per_hour
        )

    def chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> Optional[LLMResponse]:
        """Send a chat completion request to OpenRouter.

        Returns None if budget exceeded, API error, or disabled.
        """
        if not self.config.enabled or not self.config.openrouter_api_key:
            return None

        if not self.budget.can_spend(max_tokens):
            logger.warning("Token budget exceeded — skipping LLM call")
            return None

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pokemon-ai",
            "X-Title": "Pokemon AI Brain",
        }

        req = urllib.request.Request(
            OPENROUTER_API_URL, data=payload, headers=headers
        )

        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as e:
            logger.warning(f"OpenRouter API error: {e}")
            return None

        latency_ms = (time.time() - start) * 1000

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", max_tokens)
        except (KeyError, IndexError) as e:
            logger.warning(f"Unexpected API response format: {e}")
            return None

        self.budget.record(tokens)

        return LLMResponse(
            content=content,
            model=model,
            tokens_used=tokens,
            latency_ms=latency_ms,
        )
