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

    # Map IDs for intro locations (from Emerald ROM)
    MAP_INSIDE_TRUCK = (25, 40)   # Moving truck interior
    # Indoor maps in Littleroot (group 25 in pokeemerald):
    # These will be auto-detected and logged on first encounter
    MAP_HOUSE_2F = None           # Player's House 2F - detected dynamically
    MAP_HOUSE_1F = None           # Player's House 1F - detected dynamically
    MAP_RIVAL_HOUSE_1F = None     # Rival's House 1F - detected dynamically
    MAP_RIVAL_HOUSE_2F = None     # Rival's House 2F - detected dynamically
    MAP_LITTLEROOT = (0, 9)       # Littleroot Town (map group 0, map 9)
    MAP_ROUTE_101 = (0, 16)       # Route 101 (confirmed from memory_map)
    MAP_BIRCH_LAB = None          # Professor Birch's Lab - detected dynamically

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
        """Detect current intro phase from map location.
        
        Uses known map IDs where available, with robust fallback for
        unknown indoor maps during the Emerald intro sequence.
        """
        # Check for truck
        if map_loc == self.MAP_INSIDE_TRUCK:
            self._phase = IntroPhase.IN_TRUCK
            return
            
        # Check for Littleroot Town (outdoor)
        if map_loc == self.MAP_LITTLEROOT:
            if self._visited_rival_house:
                self._phase = IntroPhase.HEADING_TO_ROUTE
            else:
                self._phase = IntroPhase.LITTLEROOT_OUTSIDE
            self._littleroot_visits += 1
            return
            
        # Check for Route 101
        if map_loc == self.MAP_ROUTE_101:
            self._phase = IntroPhase.ROUTE_101
            return
            
        # For indoor maps during intro (high group numbers like 25+),
        # detect phase by the sequence of events rather than exact map IDs
        group, num = map_loc
        if group >= 4:  # Indoor map
            # Track map transitions during intro
            if self._phase == IntroPhase.IN_TRUCK and map_loc != self.MAP_INSIDE_TRUCK:
                # Just left the truck -> must be in house 2F (bedroom)
                logger.info(f"Detected Player House 2F at map {map_loc}")
                self._phase = IntroPhase.HOUSE_2F
                return
            elif self._phase == IntroPhase.HOUSE_2F and map_loc != self._last_map:
                # Left bedroom -> downstairs (1F)
                logger.info(f"Detected Player House 1F at map {map_loc}")
                self._phase = IntroPhase.HOUSE_1F
                return
            elif self._phase in (IntroPhase.LITTLEROOT_OUTSIDE, IntroPhase.HEADING_TO_ROUTE):
                if not self._visited_rival_house:
                    # Entered a building from Littleroot before visiting rival
                    logger.info(f"Detected Rival's House at map {map_loc}")
                    self._phase = IntroPhase.RIVAL_HOUSE
                    self._visited_rival_house = True
                    return
                else:
                    # Entered a building after visiting rival.
                    # Do NOT mark complete here — could be Birch's lab or just an indoor cutscene.
                    # Only party_count > 0 (checked at top of tick()) marks true completion.
                    logger.info(f"Intro: indoor map {map_loc} after rival visit (likely Birch lab) — pressing A")
                    # Stay in HEADING_TO_ROUTE; _handle_phase will press A through any dialogue
                    return
        
        # Unknown map - log periodically and stay in current phase
        if self._tick_count % 30 == 0:
            logger.info(f"Intro: unknown map {map_loc}, staying in phase {self._phase.name}")

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
        else:
            # UNKNOWN phase or unhandled - just press A to advance
            self.input.tap("A")

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
        Handle Route 101 — walk north to trigger Birch encounter, then
        press A through the bag dialogue and select Mudkip (first option).

        Sequence after walking north:
          - Birch runs in, cutscene fires (scripted)
          - Dialogue: "Help! My bag!" → press A
          - Pokeball menu appears (3 choices: Treecko, Torchic, Mudkip)
          - Mudkip is the 3rd option (Down x2, then A)
          - Confirm dialogue → A
          - Rival appears, optional battle
        """
        # Phase ticks < 60: walk north to reach tall grass / trigger encounter
        if self._phase_ticks < 60:
            self.input.walk("Up")
            return

        # After tick 60, the encounter should have triggered.
        # If we still have no party (checked in tick()), keep pressing A
        # to advance Birch's dialogue and reach the bag/starter menu.
        #
        # Mudkip selection sequence (approximate):
        #   ticks 60-120:  press A to advance Birch dialogue
        #   ticks 121-125: press Down to move cursor to Mudkip (3rd option)
        #   ticks 126-128: press Down again
        #   ticks 129-135: press A to select Mudkip
        #   ticks 136+:    press A to confirm / advance remaining dialogue
        t = self._phase_ticks
        if t < 120:
            # Advance dialogue
            if t % 4 == 0:
                self.input.tap("A")
        elif t == 121:
            self.input.tap("Down")
        elif t == 125:
            self.input.tap("Down")
        elif 129 <= t <= 132:
            if t % 2 == 0:
                self.input.tap("A")
        else:
            # Confirm everything else with A
            if t % 4 == 0:
                self.input.tap("A")
