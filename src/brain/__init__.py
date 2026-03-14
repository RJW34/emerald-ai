"""
GameBrain — LLM decision layer for Pokemon gameplay.

Called at decision points only (~10/hr). Rule engine executes the plan.
If brain is unavailable, rule engine runs as fallback. The game never stops.

Uses OPENROUTER_API_KEY exclusively — never ANTHROPIC_API_KEY.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import BrainConfig
from .decision_cache import DecisionCache
from .decision_log import DecisionLog, DecisionRecord
from .llm_client import OpenRouterClient
from .prompts import get_battle_prompt, get_strategic_prompt, get_stuck_prompt
from .replay_compiler import ReplayCompiler
from .state_formatter import StateFormatter

logger = logging.getLogger(__name__)


class GameBrain:
    """Single entry point for LLM-driven game decisions.

    Usage:
        brain = GameBrain(game_key="firered")

        # Strategic planning (returns None on failure → fall back to rule engine)
        objective = brain.get_strategic_objective(badges=2, ...)

        # Battle tactics — trainer battles only
        action = brain.get_battle_action(player=..., enemy=..., is_trainer=True)

        # Stuck recovery
        recovery = brain.get_stuck_recovery(location=..., reason=..., ...)
    """

    def __init__(
        self,
        game_key: str = "firered",
        config: Optional[BrainConfig] = None,
    ):
        self.game_key = game_key
        self.config = config or BrainConfig.from_env()
        self.client = OpenRouterClient(self.config)
        self.cache = DecisionCache(default_ttl=self.config.cache_ttl_seconds)
        self.log = DecisionLog(self.config.data_dir)
        self.replay = ReplayCompiler(self.config.data_dir)
        self.formatter = StateFormatter()

        self._last_strategic_call = 0.0
        self._last_stuck_call = 0.0

        if self.config.enabled:
            logger.info(
                f"Brain enabled: strategic={self.config.strategic_model}, "
                f"tactical={self.config.tactical_model}"
            )
        else:
            logger.info(
                "Brain disabled — rule engine will handle all decisions"
            )

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    # ------------------------------------------------------------------
    # Strategic planning (~2 calls/hr, Sonnet)
    # ------------------------------------------------------------------

    def get_strategic_objective(
        self,
        badges: int,
        current_map: tuple[int, int],
        map_name: str,
        party: list[dict],
        position: tuple[int, int],
        recent_events: list[str] = None,
    ) -> Optional[dict]:
        """Get next strategic objective from LLM.

        Returns dict with keys: objective, destination, reason, priority.
        Returns None if brain unavailable/disabled (caller falls back).
        """
        if not self.config.enabled:
            return None

        # Rate limit: min 2 minutes between strategic calls
        if time.time() - self._last_strategic_call < 120:
            return None

        cache_key = DecisionCache.make_key(
            type="strategic", badges=badges, map=current_map
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        game_name = (
            "Pokemon Emerald"
            if self.game_key == "emerald"
            else "Pokemon Fire Red"
        )
        state_text = self.formatter.format_strategic_state(
            badges=badges,
            current_map=current_map,
            map_name=map_name,
            party=party,
            position=position,
            recent_events=recent_events,
            game_name=game_name,
        )

        system_prompt = get_strategic_prompt(self.game_key)

        response = self.client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": state_text},
            ],
            model=self.config.strategic_model,
            max_tokens=300,
            temperature=0.3,
        )

        if response is None:
            return None

        self._last_strategic_call = time.time()

        decision = self._parse_json_response(response.content)
        if decision is None:
            return None

        self.cache.put(cache_key, decision, ttl=600)
        self.log.log(DecisionRecord(
            timestamp=datetime.now().isoformat(),
            type="strategic",
            model=self.config.strategic_model,
            badges=badges,
            map_group=current_map[0],
            map_num=current_map[1],
            map_name=map_name,
            position=position,
            decision=decision,
            tokens_used=response.tokens_used,
            latency_ms=response.latency_ms,
        ))

        logger.info(
            f"Brain strategic: {decision.get('objective', '?')} "
            f"-> {decision.get('destination', '?')} "
            f"({response.tokens_used} tokens, {response.latency_ms:.0f}ms)"
        )

        return decision

    # ------------------------------------------------------------------
    # Battle tactics (~5 calls/hr, Haiku or Sonnet)
    # ------------------------------------------------------------------

    def get_battle_action(
        self,
        player_pokemon: dict,
        enemy_pokemon: dict,
        is_trainer: bool,
        is_gym_leader: bool = False,
        is_rival: bool = False,
        badges: int = 0,
        current_map: tuple[int, int] = (0, 0),
        map_name: str = "",
    ) -> Optional[dict]:
        """Get battle action from LLM (trainer battles only).

        Returns dict with keys: action, move_index, pokemon_index, reason.
        Returns None if brain unavailable (caller falls back to rule engine).
        """
        if not self.config.enabled:
            return None

        if not is_trainer:
            return None

        model = (
            self.config.strategic_model
            if (is_gym_leader or is_rival)
            else self.config.tactical_model
        )

        cache_key = DecisionCache.make_key(
            type="tactical",
            player_hp=player_pokemon.get("hp", 0),
            enemy_species=enemy_pokemon.get("species", ""),
            enemy_hp=enemy_pokemon.get("hp", 0),
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        state_text = self.formatter.format_battle_state(
            player_pokemon=player_pokemon,
            enemy_pokemon=enemy_pokemon,
            is_trainer=is_trainer,
        )

        system_prompt = get_battle_prompt(self.game_key)

        response = self.client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": state_text},
            ],
            model=model,
            max_tokens=200,
            temperature=0.2,
        )

        if response is None:
            return None

        decision = self._parse_json_response(response.content)
        if decision is None:
            return None

        self.cache.put(cache_key, decision, ttl=30)
        self.log.log(DecisionRecord(
            timestamp=datetime.now().isoformat(),
            type="tactical",
            model=model,
            badges=badges,
            map_group=current_map[0],
            map_num=current_map[1],
            map_name=map_name,
            position=(0, 0),
            decision=decision,
            tokens_used=response.tokens_used,
            latency_ms=response.latency_ms,
        ))

        logger.info(
            f"Brain battle: {decision.get('action', '?')} "
            f"move={decision.get('move_index', '?')} "
            f"({decision.get('reason', '')}) "
            f"[{response.tokens_used} tokens]"
        )

        return decision

    # ------------------------------------------------------------------
    # Stuck recovery (~2 calls/hr, Haiku or Sonnet)
    # ------------------------------------------------------------------

    def get_stuck_recovery(
        self,
        location: str,
        stuck_reason: str,
        recent_attempts: list[str],
        position: tuple[int, int],
        badges: int = 0,
        current_map: tuple[int, int] = (0, 0),
        map_name: str = "",
        severity: str = "moderate",
    ) -> Optional[dict]:
        """Get stuck recovery suggestion from LLM.

        Returns dict with keys: action, reason.
        Returns None if brain unavailable (caller falls back to rule engine).
        """
        if not self.config.enabled:
            return None

        # Rate limit: min 30 seconds between stuck calls
        if time.time() - self._last_stuck_call < 30:
            return None

        model = (
            self.config.strategic_model
            if severity == "severe"
            else self.config.tactical_model
        )

        state_text = self.formatter.format_stuck_state(
            location=location,
            stuck_reason=stuck_reason,
            recent_attempts=recent_attempts,
            position=position,
        )

        system_prompt = get_stuck_prompt(self.game_key)

        response = self.client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": state_text},
            ],
            model=model,
            max_tokens=150,
            temperature=0.4,
        )

        if response is None:
            return None

        self._last_stuck_call = time.time()

        decision = self._parse_json_response(response.content)
        if decision is None:
            return None

        self.log.log(DecisionRecord(
            timestamp=datetime.now().isoformat(),
            type="stuck_recovery",
            model=model,
            badges=badges,
            map_group=current_map[0],
            map_num=current_map[1],
            map_name=map_name,
            position=position,
            decision=decision,
            tokens_used=response.tokens_used,
            latency_ms=response.latency_ms,
        ))

        logger.info(
            f"Brain recovery: {decision.get('action', '?')} "
            f"({decision.get('reason', '')}) "
            f"[{response.tokens_used} tokens]"
        )

        return decision

    # ------------------------------------------------------------------
    # Replay compilation
    # ------------------------------------------------------------------

    def compile_replay(self, output_path: Optional[Path] = None) -> str:
        """Compile decision log into Lua replay script."""
        return self.replay.compile(output_path)

    # ------------------------------------------------------------------
    # Status / monitoring
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Get brain status for monitoring."""
        return {
            "enabled": self.config.enabled,
            "game": self.game_key,
            "token_budget": self.client.budget.get_usage(),
            "cache": self.cache.get_stats(),
            "session": self.log.get_session_stats(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """Parse JSON from LLM response, handling markdown wrapping."""
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
            content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    pass
            logger.warning(
                f"Failed to parse LLM response as JSON: {content[:100]}"
            )
            return None
