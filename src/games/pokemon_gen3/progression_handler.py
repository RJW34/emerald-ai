"""
Progression Handler for Pokemon Emerald.

Tracks game progress and determines what the bot should do in the overworld.
Handles the transition from intro → first battle → lab → Route 101 → Oldale.

Game progression milestones (early game):
1. INTRO         — New game flow (title screen handler)
2. LITTLEROOT    — Post-intro, navigate to Route 101
3. BIRCH_RESCUE  — On Route 101, walk north to trigger Birch encounter
4. STARTER_BATTLE — First battle (Zigzagoon), handled by battle handler
5. RETURN_TO_LAB — After battle, go back to Birch's lab
6. GOT_POKEDEX   — Received Pokedex, heading to Route 101
7. ROUTE_101     — Traveling north through Route 101
8. OLDALE_TOWN   — Arrived at Oldale Town
9. ROUTE_102     — Heading west to Petalburg
10. FREE_ROAM    — General overworld navigation

This handler reads memory to detect which milestone we're at,
then provides movement directives for the overworld handler.
"""

import logging
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...input_controller import InputController
    from .state_detector import PokemonGen3StateDetector

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    """Current phase of game progression."""
    INTRO = auto()              # Still in intro sequence
    LITTLEROOT_PRE_STARTER = auto()  # In Littleroot, no Pokemon yet
    ROUTE_101_BIRCH = auto()    # Walking north on Route 101 to trigger Birch
    STARTER_BATTLE = auto()     # In the Zigzagoon battle
    POST_BATTLE = auto()        # Just won, on Route 101 with starter
    RETURN_TO_LAB = auto()      # Walking back to Birch's lab
    IN_LAB = auto()             # In Birch's lab getting Pokedex
    GOT_POKEDEX = auto()        # Have Pokedex, heading out
    ROUTE_101_NORTH = auto()    # Traveling Route 101 toward Oldale
    OLDALE_TOWN = auto()        # In Oldale Town
    ROUTE_103_RIVAL = auto()    # Rival battle on Route 103
    ROUTE_102_WEST = auto()     # Heading west to Petalburg
    FREE_ROAM = auto()          # General exploration


class MovementDirective:
    """
    A simple movement instruction for the overworld handler.

    Provides a direction to walk and optional target coordinates.
    """

    def __init__(
        self,
        direction: str,
        description: str = "",
        priority: bool = True,
    ):
        """
        Args:
            direction: Primary direction to walk (Up/Down/Left/Right)
            description: Human-readable description of what we're doing
            priority: If True, this overrides random exploration
        """
        self.direction = direction
        self.description = description
        self.priority = priority


class ProgressionHandler:
    """
    Determines game phase and provides movement directives.

    Reads game memory to figure out where we are in the story,
    then tells the overworld handler which direction to go.
    """

    # Map constants
    MAP_LITTLEROOT = (0, 9)
    MAP_ROUTE_101 = (0, 16)
    MAP_ROUTE_102 = (0, 17)
    MAP_ROUTE_103 = (0, 18)
    MAP_OLDALE = (0, 10)
    MAP_PETALBURG = (0, 0)
    MAP_BIRCH_LAB = (1, 4)
    MAP_PLAYER_HOUSE_1F = (1, 0)
    MAP_PLAYER_HOUSE_2F = (1, 1)

    def __init__(
        self,
        state_detector: "PokemonGen3StateDetector",
        input_controller: "InputController",
    ):
        self.state = state_detector
        self.input = input_controller
        self._phase = GamePhase.INTRO
        self._last_phase = GamePhase.INTRO
        self._tick_count = 0

        # Track whether we've gotten the Pokedex
        self._has_pokedex = False

    @property
    def phase(self) -> GamePhase:
        return self._phase

    def detect_phase(self) -> GamePhase:
        """
        Detect current game phase from memory state.

        Returns:
            Current GamePhase
        """
        try:
            map_loc = self.state.get_map_location()
            party_count = self.state.get_party_count()
        except Exception:
            return self._phase  # Keep current phase on read failure

        # Check event flags for progression
        has_pokemon = party_count > 0
        has_pokedex = self.state.get_event_flag(0x861)  # FLAG_SYS_POKEDEX_GET
        has_starter_flag = self.state.get_event_flag(0x860)  # FLAG_SYS_POKEMON_GET

        # Update Pokedex tracking
        if has_pokedex:
            self._has_pokedex = True

        # Determine phase
        old_phase = self._phase

        if not has_pokemon and not has_starter_flag:
            # No Pokemon yet
            if map_loc == self.MAP_ROUTE_101:
                self._phase = GamePhase.ROUTE_101_BIRCH
            elif map_loc == self.MAP_LITTLEROOT:
                self._phase = GamePhase.LITTLEROOT_PRE_STARTER
            elif map_loc in (self.MAP_PLAYER_HOUSE_1F, self.MAP_PLAYER_HOUSE_2F):
                self._phase = GamePhase.INTRO
            else:
                self._phase = GamePhase.INTRO

        elif has_pokemon and not has_pokedex:
            # Have starter but no Pokedex
            if map_loc == self.MAP_ROUTE_101:
                self._phase = GamePhase.POST_BATTLE
            elif map_loc == self.MAP_LITTLEROOT:
                self._phase = GamePhase.RETURN_TO_LAB
            elif map_loc == self.MAP_BIRCH_LAB:
                self._phase = GamePhase.IN_LAB
            else:
                self._phase = GamePhase.POST_BATTLE

        elif has_pokemon and has_pokedex:
            # Have Pokedex — main gameplay
            if map_loc == self.MAP_BIRCH_LAB:
                self._phase = GamePhase.GOT_POKEDEX
            elif map_loc == self.MAP_LITTLEROOT:
                self._phase = GamePhase.GOT_POKEDEX
            elif map_loc == self.MAP_ROUTE_101:
                self._phase = GamePhase.ROUTE_101_NORTH
            elif map_loc == self.MAP_OLDALE:
                self._phase = GamePhase.OLDALE_TOWN
            elif map_loc == self.MAP_ROUTE_103:
                self._phase = GamePhase.ROUTE_103_RIVAL
            elif map_loc == self.MAP_ROUTE_102:
                self._phase = GamePhase.ROUTE_102_WEST
            elif map_loc == self.MAP_PETALBURG:
                self._phase = GamePhase.FREE_ROAM
            else:
                self._phase = GamePhase.FREE_ROAM

        if self._phase != old_phase:
            logger.info(f"Game phase: {old_phase.name} → {self._phase.name}")

        self._last_phase = self._phase
        return self._phase

    def get_directive(self) -> Optional[MovementDirective]:
        """
        Get movement directive for current phase.

        Returns:
            MovementDirective telling the overworld where to go,
            or None if no specific direction needed (free roam).
        """
        self._tick_count += 1

        if self._phase == GamePhase.LITTLEROOT_PRE_STARTER:
            # Walk north to Route 101
            return MovementDirective("Up", "Walking north to Route 101")

        elif self._phase == GamePhase.ROUTE_101_BIRCH:
            # Walk north to trigger Birch encounter
            return MovementDirective("Up", "Walking north to trigger Birch encounter")

        elif self._phase == GamePhase.POST_BATTLE:
            # Walk south back to Littleroot
            return MovementDirective("Down", "Returning south to Littleroot Town")

        elif self._phase == GamePhase.RETURN_TO_LAB:
            # Walk toward Birch's lab in Littleroot
            # Lab is in the middle-right area of town
            # Walk right and try to enter
            if self._tick_count % 20 < 10:
                return MovementDirective("Right", "Walking to Birch's Lab")
            else:
                return MovementDirective("Up", "Walking to Birch's Lab entrance")

        elif self._phase == GamePhase.IN_LAB:
            # In lab — dialogue will handle this (press A)
            return None

        elif self._phase == GamePhase.GOT_POKEDEX:
            # Head north to Route 101
            return MovementDirective("Up", "Heading north with Pokedex")

        elif self._phase == GamePhase.ROUTE_101_NORTH:
            # Walk north through Route 101 to Oldale
            return MovementDirective("Up", "Traveling Route 101 to Oldale Town")

        elif self._phase == GamePhase.OLDALE_TOWN:
            # In Oldale, head west to Route 102
            # First visit: NPC will give tour, just press A through it
            # Could also go north to Route 103 for rival battle
            return MovementDirective("Left", "Heading west from Oldale")

        elif self._phase == GamePhase.ROUTE_103_RIVAL:
            # Route 103 — walk north/right to find rival
            return MovementDirective("Right", "Heading to rival on Route 103")

        elif self._phase == GamePhase.ROUTE_102_WEST:
            # Walk west through Route 102 to Petalburg
            return MovementDirective("Left", "Traveling Route 102 to Petalburg")

        # FREE_ROAM or unknown — no directive
        return None
