"""
Autonomous Learning Loop

Orchestrates all learning systems:
- Stuck detection
- Error recovery
- Coordinate learning
- Vision analysis
- Path optimization
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..input_controller import InputController
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector
    from ..emulator.bizhawk_client import BizHawkClient

from .stuck_detector import StuckDetector, StuckReason
from .error_recovery import ErrorRecoverySystem, RecoveryLevel
from .coordinate_learner import CoordinateLearner
from .vision_analyzer import VisionAnalyzer
from .database import get_database

logger = logging.getLogger(__name__)


@dataclass
class LearningMetrics:
    """Metrics tracking autonomous learning performance."""
    total_ticks: int = 0
    stuck_events: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    coordinates_learned: int = 0
    obstacles_discovered: int = 0
    vision_api_calls: int = 0

    @property
    def recovery_rate(self) -> float:
        """Calculate recovery success rate."""
        total = self.successful_recoveries + self.failed_recoveries
        if total == 0:
            return 0.0
        return self.successful_recoveries / total


class AutonomousLearningLoop:
    """
    Main orchestrator for autonomous learning.

    Usage:
        loop = AutonomousLearningLoop(
            state_detector, input_controller, bizhawk_client
        )

        # In game tick:
        loop.tick()

        # Get metrics:
        metrics = loop.metrics
    """

    def __init__(self,
                 state_detector: "PokemonGen3StateDetector",
                 input_controller: "InputController",
                 bizhawk_client: "BizHawkClient",
                 enable_vision: bool = True,
                 brain=None):
        """
        Initialize the autonomous learning loop.

        Args:
            state_detector: Game state detector
            input_controller: Input controller
            bizhawk_client: BizHawk client (for vision screenshots)
            enable_vision: Whether to enable Vision API
            brain: Optional GameBrain instance for LLM-assisted recovery
        """
        self.state_detector = state_detector
        self.input = input_controller

        # Initialize learning systems
        self.stuck_detector = StuckDetector(state_detector)
        self.coordinate_learner = CoordinateLearner(state_detector)

        if enable_vision:
            self.vision_analyzer: Optional[VisionAnalyzer] = VisionAnalyzer(bizhawk_client)
        else:
            self.vision_analyzer = None

        self.error_recovery = ErrorRecoverySystem(
            self.stuck_detector,
            input_controller,
            state_detector,
            self.vision_analyzer,
            brain=brain,
        )

        self.db = get_database()

        # Metrics
        self.metrics = LearningMetrics()
        self._tick_count = 0

        # Recovery tracking
        self._was_stuck = False
        self._recovery_start_tick: int = 0

    def tick(self, attempted_direction: Optional[str] = None) -> dict:
        """
        Execute one learning loop tick.

        Args:
            attempted_direction: Direction bot tried to move (if any)

        Returns:
            Dictionary with learning status:
            {
                "stuck": bool,
                "stuck_reason": str,
                "recovering": bool,
                "learning": dict of what was learned this tick
            }
        """
        self._tick_count += 1
        self.metrics.total_ticks = self._tick_count

        result = {
            "stuck": False,
            "stuck_reason": "",
            "recovering": False,
            "recovery_level": "",
            "vision_used": False,
            "learning": {}
        }

        # Update stuck detection
        self.stuck_detector.update(self._tick_count, attempted_direction)

        # Update coordinate learning
        self.coordinate_learner.update()

        # Handle stuck state
        if self.stuck_detector.is_stuck:
            result["stuck"] = True
            result["stuck_reason"] = self.stuck_detector.stuck_reason.name
            result["recovery_level"] = self.error_recovery._current_level.name

            if not self._was_stuck:
                # Just became stuck
                self.metrics.stuck_events += 1
                self._recovery_start_tick = self._tick_count
                logger.info(f"Learning loop: Became stuck ({result['stuck_reason']})")

            # Check if we're about to use vision
            if self.error_recovery._current_level == RecoveryLevel.VISION:
                result["vision_used"] = True
                self.metrics.vision_api_calls += 1

            # Attempt recovery
            result["recovering"] = self.error_recovery.attempt_recovery()
            self._was_stuck = True

        else:
            # Not stuck
            if self._was_stuck:
                # Just recovered
                self.metrics.successful_recoveries += 1
                self.error_recovery.record_recovery_outcome(success=True)
                recovery_ticks = self._tick_count - self._recovery_start_tick
                logger.info(f"Learning loop: Recovered after {recovery_ticks} ticks")

            self._was_stuck = False

        return result

    def force_vision_analysis(self, context: str = "") -> Optional[dict]:
        """
        Force a Vision API analysis.

        Use for debugging or when extra analysis is needed.
        """
        if not self.vision_analyzer or not self.vision_analyzer.is_available:
            return None

        self.metrics.vision_api_calls += 1
        return self.vision_analyzer.analyze_stuck_situation(context)

    def get_learning_summary(self) -> dict:
        """Get summary of what has been learned."""
        stats = self.db.get_statistics()

        return {
            "metrics": {
                "total_ticks": self.metrics.total_ticks,
                "stuck_events": self.metrics.stuck_events,
                "recovery_rate": f"{self.metrics.recovery_rate:.1%}",
            },
            "database": stats,
            "vision_available": self.vision_analyzer.is_available if self.vision_analyzer else False,
            "vision_calls_remaining": self.vision_analyzer.daily_calls_remaining if self.vision_analyzer else 0
        }

    def reset_metrics(self) -> None:
        """Reset learning metrics."""
        self.metrics = LearningMetrics()
        self._tick_count = 0
