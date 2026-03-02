"""
Input Controller - Wrapper for emulator button inputs.

Provides a consistent interface for sending button inputs to the emulator,
abstracting away the underlying IPC mechanism (BizHawk file-based IPC).
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .emulator.bizhawk_client import BizHawkClient

logger = logging.getLogger(__name__)


class InputController:
    """
    Controller for sending button inputs to the emulator.

    Wraps the BizHawk client's button methods with additional features:
    - Input logging
    - Cooldown between inputs to prevent input eating
    - Hold duration support
    """

    # Valid button names
    VALID_BUTTONS = {"A", "B", "Start", "Select", "Up", "Down", "Left", "Right", "L", "R"}

    def __init__(self, client: "BizHawkClient", input_cooldown: float = 0.05):
        """
        Initialize the input controller.

        Args:
            client: BizHawk client for sending inputs
            input_cooldown: Minimum time between inputs in seconds
        """
        self.client = client
        self.input_cooldown = input_cooldown
        self._last_input_time = 0.0
        self._walking_direction = None

    def tap(self, button: str) -> bool:
        """
        Tap a button (press and release).

        Args:
            button: Button name (A, B, Start, Select, Up, Down, Left, Right, L, R)

        Returns:
            True if input was sent successfully
        """
        if button not in self.VALID_BUTTONS:
            logger.warning(f"Invalid button: {button}")
            return False

        # Enforce cooldown between inputs
        now = time.time()
        elapsed = now - self._last_input_time
        if elapsed < self.input_cooldown:
            time.sleep(self.input_cooldown - elapsed)

        result = self.client.tap_button(button)
        self._last_input_time = time.time()

        logger.debug(f"Input: {button}")
        return result

    def hold(self, button: str, frames: int = 30) -> bool:
        """
        Hold a button for a specified number of frames.

        Args:
            button: Button name
            frames: Number of frames to hold (60 fps = 1 second)

        Returns:
            True if input was sent successfully
        """
        if button not in self.VALID_BUTTONS:
            logger.warning(f"Invalid button: {button}")
            return False

        result = self.client.hold_button(button, frames)
        self._last_input_time = time.time()

        logger.debug(f"Hold: {button} for {frames} frames")
        return result

    def walk(self, direction: str, frames: int = 16) -> bool:
        """
        Walk in a direction by holding the d-pad.

        Used by the learning module's overworld navigation and error recovery
        systems for continuous movement rather than single-frame taps.

        Args:
            direction: Direction to walk (Up, Down, Left, Right)
            frames: Number of frames to hold direction (default 16 = ~0.27s at 60fps)

        Returns:
            True if input was sent successfully
        """
        if direction not in ("Up", "Down", "Left", "Right"):
            logger.warning(f"Invalid walk direction: {direction}")
            return False

        self._walking_direction = direction
        return self.hold(direction, frames)

    def stop_walking(self) -> None:
        """
        Stop any current walking movement.

        Called by the learning module's error recovery system before
        attempting recovery actions, and by the overworld handler when
        reaching a navigation target.
        """
        self._walking_direction = None
        # Release all directional inputs by sending a neutral frame
        # (BizHawk will stop holding after the hold duration expires,
        # but this ensures we don't queue another walk)

    def press_sequence(self, buttons: list[str], delay: float = 0.1) -> bool:
        """
        Press a sequence of buttons with delay between each.

        Args:
            buttons: List of button names to press in order
            delay: Delay between button presses in seconds

        Returns:
            True if all inputs were sent successfully
        """
        success = True
        for button in buttons:
            if not self.tap(button):
                success = False
            time.sleep(delay)
        return success
