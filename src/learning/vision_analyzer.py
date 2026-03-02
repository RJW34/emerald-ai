"""
Vision API Integration

Analyzes screenshots using Claude's Vision API for:
- Stuck detection and recovery suggestions
- Visual puzzle solving
- Dialogue/menu state detection
- Map exploration assistance
"""

import base64
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

if TYPE_CHECKING:
    from ..emulator.bizhawk_client import BizHawkClient

logger = logging.getLogger(__name__)

# Screenshot directory
SCREENSHOT_DIR = Path(__file__).parent.parent.parent / "debug_screenshots"


class VisionAnalyzer:
    """
    Analyzes game screenshots using Claude Vision API.

    Usage:
        analyzer = VisionAnalyzer(client)

        # Analyze current game state
        result = analyzer.analyze_situation(context="Bot appears stuck")

        # Get recovery suggestion
        action = analyzer.suggest_recovery_action()
    """

    # Rate limiting
    MIN_ANALYSIS_INTERVAL = 5.0  # Minimum seconds between API calls
    MAX_DAILY_CALLS = 100        # Maximum API calls per day

    # Prompts
    STUCK_ANALYSIS_PROMPT = """You are analyzing a Pokemon Emerald game screenshot.

The bot is currently STUCK and needs help. Analyze the image and provide:

1. CURRENT STATE: What do you see on screen? (overworld, battle, menu, dialogue, etc.)
2. VISIBLE OBSTACLES: Any walls, NPCs, or objects blocking movement?
3. PLAYER POSITION: Where is the player character on screen?
4. SUGGESTED ACTION: What button press or direction would help?

Be specific and concise. Format your response as:
STATE: <state>
OBSTACLES: <obstacles or "none visible">
POSITION: <description>
ACTION: <specific button or direction, e.g., "Press A", "Move Up", "Press B to cancel">
REASONING: <brief explanation>
"""

    GENERAL_ANALYSIS_PROMPT = """You are analyzing a Pokemon Emerald game screenshot.

Describe what you see:
1. Current game state (overworld, battle, menu, dialogue, etc.)
2. Any text visible on screen
3. Player character location (if visible)
4. Any notable features or obstacles

Be concise and factual.
"""

    def __init__(self, bizhawk_client: "BizHawkClient", api_key: Optional[str] = None):
        """
        Initialize the vision analyzer.

        Args:
            bizhawk_client: BizHawk client for screenshot capture
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
        """
        self.client = bizhawk_client
        self._api_key = api_key
        self._anthropic: Optional["Anthropic"] = None

        # Rate limiting
        self._last_call_time: float = 0
        self._daily_call_count: int = 0
        self._call_count_date: str = ""

        # Ensure screenshot directory exists
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize API client
        if ANTHROPIC_AVAILABLE:
            self._init_anthropic()
        else:
            logger.warning("Anthropic package not installed - Vision API unavailable")

    def _init_anthropic(self) -> None:
        """Initialize the Anthropic client."""
        import os
        api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            self._anthropic = Anthropic(api_key=api_key)
            logger.info("Vision API initialized")
        else:
            logger.warning("No ANTHROPIC_API_KEY found - Vision API unavailable")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        # Check daily limit
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._call_count_date:
            self._daily_call_count = 0
            self._call_count_date = today

        if self._daily_call_count >= self.MAX_DAILY_CALLS:
            logger.warning("Daily Vision API limit reached")
            return False

        # Check interval
        elapsed = time.time() - self._last_call_time
        if elapsed < self.MIN_ANALYSIS_INTERVAL:
            logger.debug(f"Rate limiting: {self.MIN_ANALYSIS_INTERVAL - elapsed:.1f}s remaining")
            return False

        return True

    def _capture_screenshot(self) -> Optional[Path]:
        """Capture a screenshot and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = SCREENSHOT_DIR / f"vision_{timestamp}.png"

        if self.client.save_screenshot(str(filepath)):
            return filepath
        return None

    def _encode_image(self, filepath: Path) -> str:
        """Encode image to base64."""
        with open(filepath, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _call_vision_api(self, image_path: Path, prompt: str) -> Optional[str]:
        """Call the Vision API with an image and prompt."""
        if not self._anthropic:
            logger.error("Vision API not available")
            return None

        if not self._check_rate_limit():
            return None

        try:
            image_data = self._encode_image(image_path)

            message = self._anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ],
                    }
                ],
            )

            # Update rate limiting
            self._last_call_time = time.time()
            self._daily_call_count += 1

            response_text = message.content[0].text
            logger.info(f"Vision API response received ({len(response_text)} chars)")

            return response_text

        except Exception as e:
            logger.error(f"Vision API call failed: {e}")
            return None

    def analyze_stuck_situation(self, context: str = "") -> Optional[dict]:
        """
        Analyze the current game state when stuck.

        Args:
            context: Additional context about the stuck situation

        Returns:
            Dictionary with STATE, OBSTACLES, POSITION, ACTION, REASONING
            or None if analysis failed
        """
        # Capture screenshot
        screenshot = self._capture_screenshot()
        if not screenshot:
            logger.error("Failed to capture screenshot for analysis")
            return None

        # Build prompt with context
        prompt = self.STUCK_ANALYSIS_PROMPT
        if context:
            prompt += f"\n\nAdditional context: {context}"

        # Call API
        response = self._call_vision_api(screenshot, prompt)
        if not response:
            return None

        # Parse response
        return self._parse_stuck_response(response)

    def _parse_stuck_response(self, response: str) -> dict:
        """Parse the structured stuck analysis response."""
        result = {
            "state": "",
            "obstacles": "",
            "position": "",
            "action": "",
            "reasoning": "",
            "raw": response
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("STATE:"):
                result["state"] = line[6:].strip()
            elif line.startswith("OBSTACLES:"):
                result["obstacles"] = line[10:].strip()
            elif line.startswith("POSITION:"):
                result["position"] = line[9:].strip()
            elif line.startswith("ACTION:"):
                result["action"] = line[7:].strip()
            elif line.startswith("REASONING:"):
                result["reasoning"] = line[10:].strip()

        return result

    def analyze_general(self, prompt: Optional[str] = None) -> Optional[str]:
        """
        General screenshot analysis.

        Args:
            prompt: Custom prompt, or uses default general analysis

        Returns:
            Analysis text or None if failed
        """
        screenshot = self._capture_screenshot()
        if not screenshot:
            return None

        return self._call_vision_api(screenshot, prompt or self.GENERAL_ANALYSIS_PROMPT)

    def suggest_recovery_action(self, stuck_reason: str) -> Optional[str]:
        """
        Get a suggested action to recover from being stuck.

        Args:
            stuck_reason: Why the bot is stuck (from StuckDetector)

        Returns:
            Suggested action string (e.g., "Up", "A", "B") or None
        """
        result = self.analyze_stuck_situation(context=f"Stuck reason: {stuck_reason}")
        if result and result.get("action"):
            # Extract just the button/direction from the action
            action = result["action"].upper()

            # Parse common responses
            if "PRESS A" in action or action == "A":
                return "A"
            elif "PRESS B" in action or action == "B":
                return "B"
            elif "MOVE UP" in action or "UP" in action:
                return "Up"
            elif "MOVE DOWN" in action or "DOWN" in action:
                return "Down"
            elif "MOVE LEFT" in action or "LEFT" in action:
                return "Left"
            elif "MOVE RIGHT" in action or "RIGHT" in action:
                return "Right"
            elif "START" in action:
                return "Start"
            elif "SELECT" in action:
                return "Select"

            # Return raw action if can't parse
            return result["action"]

        return None

    @property
    def is_available(self) -> bool:
        """Check if Vision API is available."""
        return self._anthropic is not None

    @property
    def daily_calls_remaining(self) -> int:
        """Get remaining daily API calls."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._call_count_date:
            return self.MAX_DAILY_CALLS
        return max(0, self.MAX_DAILY_CALLS - self._daily_call_count)
