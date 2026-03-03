"""
Intro Handler for Pokemon Emerald.

Manages the post-title-screen intro sequence:
  Truck → Mom's House → Set Clock → Downstairs → Outside →
  Rival's House → Outside → Walk north → Route 101

The game auto-plays many of these transitions with scripted events.
Our job is to:
1. Detect where we are in the intro via map + flags
2. Press A through dialogue and cutscenes
3. Walk in the right direction when control is given back
4. Recognize when intro is "complete" (player on Route 101 or Littleroot overworld)

Key maps (from map_data.py / pokeemerald disassembly):
  Inside Truck:           indoor (the game auto-exits after a script)
  Player House 2F:        (1, 1) Brendan's House 2F — set clock here
  Player House 1F:        (1, 0) Brendan's House 1F — Mom dialogue
  Littleroot Town:        (0, 9) — overworld hub during intro
  Rival House:            (1, 2) or (1, 3) — May's house
  Route 101:              (0, 16)
  Birch's Lab:            (1, 4)

Strategy: The intro is heavily scripted. Most of it auto-plays if we
just press A through all dialogue. The few times we get overworld control:
  - In house 2F: walk to clock (handled by script trigger)
  - Downstairs: walk to door, go outside
  - Outside: walk to rival's house, then north to Route 101
  - Route 101: walk north to trigger Birch encounter

We use a simple state machine that tracks map transitions.
"""

import logging
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...input_controller import InputController
    from .state_detector import PokemonGen3StateDetector

logger = logging.getLogger(__name__)


class IntroPhase(Enum):
    """Phases of the Emerald intro sequence."""
    UNKNOWN = auto()
    IN_TRUCK = auto()           # Inside the moving truck
    HOUSE_2F = auto()           # Player's bedroom — set clock
    HOUSE_1F = auto()           # Downstairs — Mom dialogue, TV
    LITTLEROOT_OUTSIDE = auto() # Outside in Littleroot Town
    RIVAL_HOUSE = auto()        # Visiting rival's house
    HEADING_TO_ROUTE = auto()   # Walking north toward Route 101
    ROUTE_101 = auto()          # On Route 101 — Birch encounter
    INTRO_COMPLETE = auto()     # Intro is done (have starter or in lab)


class IntroHandler:
    """
    Handles the Pokemon Emerald intro sequence.

    Detects current phase from map/memory and advances the intro
    by pressing A through dialogue and walking to the right places.

    Usage:
        handler = IntroHandler(state_detector, input_controller)

        # In game loop when intro isn't complete:
        if not handler.is_complete:
            handler.tick()
    """

    # Map IDs for intro locations
    # Player house (Brendan's house in Littleroot)
    MAP_HOUSE_2F = (1, 1)      # Brendan's House 2F
    MAP_HOUSE_1F = (1, 0)      # Brendan's House 1F
    MAP_RIVAL_HOUSE_1F = (1, 2)  # May's House 1F
    MAP_RIVAL_HOUSE_2F = (1, 3)  # May's House 2F
    MAP_LITTLEROOT = (0, 9)    # Littleroot Town
    MAP_ROUTE_101 = (0, 16)    # Route 101
    MAP_BIRCH_LAB = (1, 4)     # Professor Birch's Lab

    def __init__(
        self,
        state_detector: "PokemonGen3StateDetector",
        input_controller: "InputController",
    ):
        self.state = state_detector
        self.input = input_controller

        self._phase = IntroPhase.UNKNOWN
        self._is_complete = False
        self._tick_count = 0
        self._phase_ticks = 0  # ticks in current phase
        self._last_map = (0, 0)

        # Walking state
        self._walk_direction: Optional[str] = None
        self._walk_ticks = 0
        self._walk_target_ticks = 0

        # Track visits for progression
        self._visited_rival_house = False
        self._littleroot_visits = 0

    @property
    def is_complete(self) -> bool:
        """Check if the intro sequence is complete."""
        return self._is_complete

    @property
    def phase(self) -> IntroPhase:
        return self._phase

    def tick(self) -> None:
        """Execute one intro tick. Call every game loop iteration."""
        self._tick_count += 1
        self._phase_ticks += 1

        # Read current map
        try:
            map_loc = self.state.get_map_location()
            party_count = self.state.get_party_count()
        except Exception as e:
            logger.debug(f"Intro handler: failed to read state: {e}")
            # During early intro, memory may not be valid — just press A
            self.input.tap("A")
            return

        # If we have a Pokemon, intro is done
        if party_count > 0:
            logger.info("✓ INTRO COMPLETE — player has a Pokemon in party!")
            self._phase = IntroPhase.INTRO_COMPLETE
            self._is_complete = True
            return

        # Detect phase from current map
        old_phase = self._phase
        self._detect_phase(map_loc)

        if self._phase != old_phase:
            logger.info(f"Intro phase: {old_phase.name} → {self._phase.name} (map={map_loc})")
            self._phase_ticks = 0

        # Check if intro is complete
        if self._phase == IntroPhase.INTRO_COMPLETE:
            self._is_complete = True
            return

        # Handle current phase
        self._handle_phase(map_loc)
        self._last_map = map_loc

    def _detect_phase(self, map_loc: tuple[int, int]) -> None:
        """Detect current intro phase from map location."""
        if map_loc == self.MAP_HOUSE_2F:
            self._phase = IntroPhase.HOUSE_2F
        elif map_loc == self.MAP_HOUSE_1F:
            self._phase = IntroPhase.HOUSE_1F
        elif map_loc == self.MAP_LITTLEROOT:
            if self._visited_rival_house:
                self._phase = IntroPhase.HEADING_TO_ROUTE
            else:
                self._phase = IntroPhase.LITTLEROOT_OUTSIDE
            self._littleroot_visits += 1
        elif map_loc in (self.MAP_RIVAL_HOUSE_1F, self.MAP_RIVAL_HOUSE_2F):
            self._phase = IntroPhase.RIVAL_HOUSE
            self._visited_rival_house = True
        elif map_loc == self.MAP_ROUTE_101:
            self._phase = IntroPhase.ROUTE_101
        elif map_loc == self.MAP_BIRCH_LAB:
            # In the lab = intro is complete (post-battle, getting Pokedex)
            self._phase = IntroPhase.INTRO_COMPLETE
        else:
            # Unknown indoor map = probably still in truck or early intro
            if self._phase == IntroPhase.UNKNOWN:
                self._phase = IntroPhase.IN_TRUCK

    def _handle_phase(self, map_loc: tuple[int, int]) -> None:
        """Handle the current intro phase."""
        # Check if dialogue is active — if so, press A to advance
        if self.state.is_dialogue_active():
            self._press_a_for_dialogue()
            return

        # Check if script is locking field controls
        try:
            script_lock = self.state.client.read8(0x03000F2C)
            if script_lock != 0:
                # Script is running — press A to advance it
                if self._phase_ticks % 3 == 0:
                    self.input.tap("A")
                return
        except Exception:
            pass

        # Phase-specific handling (only when we have overworld control)
        if self._phase == IntroPhase.IN_TRUCK:
            self._handle_truck()
        elif self._phase == IntroPhase.HOUSE_2F:
            self._handle_house_2f()
        elif self._phase == IntroPhase.HOUSE_1F:
            self._handle_house_1f()
        elif self._phase == IntroPhase.LITTLEROOT_OUTSIDE:
            self._handle_littleroot_first()
        elif self._phase == IntroPhase.RIVAL_HOUSE:
            self._handle_rival_house()
        elif self._phase == IntroPhase.HEADING_TO_ROUTE:
            self._handle_heading_to_route()
        elif self._phase == IntroPhase.ROUTE_101:
            self._handle_route_101()

    def _press_a_for_dialogue(self) -> None:
        """Press A to advance dialogue, with slight spacing."""
        if self._phase_ticks % 2 == 0:
            self.input.tap("A")

    def _handle_truck(self) -> None:
        """Handle the moving truck — just press A and wait for script."""
        self.input.tap("A")

    def _handle_house_2f(self) -> None:
        """
        Handle player's bedroom (2F).

        Player needs to:
        1. Walk to the clock on the wall (scripted trigger area)
        2. Set the clock (press A through it)
        3. Walk downstairs

        The clock is typically at the top of the room. After setting it,
        we need to go down to the stairs.
        """
        # Walk down toward the stairs — the clock event triggers automatically
        # when you walk near it, and after setting it, we go downstairs
        if self._phase_ticks < 10:
            # Walk down to reach the stairs
            self.input.walk("Down")
        elif self._phase_ticks < 15:
            self.input.walk("Left")
        else:
            # If we're still here, try walking down more (stairs are usually bottom-left)
            self.input.walk("Down")

    def _handle_house_1f(self) -> None:
        """
        Handle downstairs (1F).

        Mom will talk about the TV. After dialogue, walk to the door (south).
        """
        # Walk south to exit through the door
        self.input.walk("Down")

    def _handle_littleroot_first(self) -> None:
        """
        Handle first time outside in Littleroot Town.

        Need to visit rival's house. The rival's house is typically
        to the left/west of the player's house.
        """
        pos = self.state.get_player_position()

        # Walk left toward rival's house, then up to enter it
        if self._phase_ticks < 15:
            self.input.walk("Left")
        elif self._phase_ticks < 25:
            self.input.walk("Up")
        else:
            # Try entering the door (face it and press A, or just walk into it)
            # Reset and try again
            self._phase_ticks = 0

    def _handle_rival_house(self) -> None:
        """
        Handle visiting rival's house.

        Just press A through any dialogue, then walk south to leave.
        """
        if self._phase_ticks > 20:
            # We've been here a while, try to leave
            self.input.walk("Down")

    def _handle_heading_to_route(self) -> None:
        """
        Handle walking north through Littleroot Town to Route 101.

        Route 101 is north of Littleroot Town.
        """
        # Walk north — Route 101 is at the top of Littleroot
        self.input.walk("Up")

    def _handle_route_101(self) -> None:
        """
        Handle Route 101 — walk north to trigger Birch encounter.

        The Birch encounter triggers when you walk into the tall grass
        area at the north end of Route 101. Just keep walking north.
        """
        # Walk north to trigger the Birch encounter script
        self.input.walk("Up")
