"""
Tests for IntroHandler and ProgressionHandler.

Uses mock state detector and input controller to verify:
- Phase detection from map locations
- Movement directives for each phase
- Intro completion detection
- Progression through early game milestones
"""

import pytest
from unittest.mock import MagicMock, PropertyMock, patch


class MockStateDetector:
    """Mock state detector for testing handlers."""

    def __init__(self):
        self._map_location = (0, 9)  # Littleroot Town
        self._player_position = (5, 5)
        self._party_count = 0
        self._event_flags = {}
        self._dialogue_active = False
        self.client = MagicMock()
        # Script lock defaults to 0 (no script running)
        self.client.read8.return_value = 0

    def get_map_location(self):
        return self._map_location

    def get_player_position(self):
        return self._player_position

    def get_party_count(self):
        return self._party_count

    def get_event_flag(self, flag_id):
        return self._event_flags.get(flag_id, False)

    def is_dialogue_active(self):
        return self._dialogue_active


class MockInputController:
    """Mock input controller that records all inputs."""

    def __init__(self):
        self.inputs = []
        self.walks = []
        self.taps = []

    def tap(self, button):
        self.taps.append(button)
        self.inputs.append(("tap", button))
        return True

    def walk(self, direction, frames=16):
        self.walks.append(direction)
        self.inputs.append(("walk", direction))
        return True

    def stop_walking(self):
        self.inputs.append(("stop",))

    def hold(self, button, frames=30):
        self.inputs.append(("hold", button, frames))
        return True


# ============================================================================
# IntroHandler Tests
# ============================================================================

class TestIntroHandler:
    """Tests for the intro sequence handler."""

    def _make_handler(self):
        from src.games.pokemon_gen3.intro_handler import IntroHandler
        state = MockStateDetector()
        inp = MockInputController()
        handler = IntroHandler(state, inp)
        return handler, state, inp

    def test_not_complete_initially(self):
        handler, _, _ = self._make_handler()
        assert not handler.is_complete

    def test_complete_when_party_has_pokemon(self):
        handler, state, _ = self._make_handler()
        state._party_count = 1
        handler.tick()
        assert handler.is_complete

    def test_detects_house_2f(self):
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 1)  # Brendan's House 2F
        handler.tick()
        assert handler.phase == IntroPhase.HOUSE_2F

    def test_detects_house_1f(self):
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 0)  # Brendan's House 1F
        handler.tick()
        assert handler.phase == IntroPhase.HOUSE_1F

    def test_detects_littleroot(self):
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)  # Littleroot Town
        handler.tick()
        assert handler.phase == IntroPhase.LITTLEROOT_OUTSIDE

    def test_detects_route_101(self):
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)  # Route 101
        handler.tick()
        assert handler.phase == IntroPhase.ROUTE_101

    def test_detects_rival_house(self):
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 2)  # May's House 1F
        handler.tick()
        assert handler.phase == IntroPhase.RIVAL_HOUSE

    def test_after_rival_house_heading_to_route(self):
        """After visiting rival's house and returning to Littleroot, should head to route."""
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()

        # Visit rival's house
        state._map_location = (1, 2)
        handler.tick()
        assert handler.phase == IntroPhase.RIVAL_HOUSE

        # Back in Littleroot
        state._map_location = (0, 9)
        handler.tick()
        assert handler.phase == IntroPhase.HEADING_TO_ROUTE

    def test_walks_north_on_route_101(self):
        """On Route 101, should walk north to trigger Birch encounter."""
        handler, state, inp = self._make_handler()
        state._map_location = (0, 16)  # Route 101
        handler.tick()
        # Should have walked Up
        assert "Up" in inp.walks

    def test_presses_a_during_dialogue(self):
        """Should press A when dialogue is active."""
        handler, state, inp = self._make_handler()
        state._map_location = (0, 9)
        state._dialogue_active = True
        handler.tick()
        assert "A" in inp.taps

    def test_birch_lab_completes_intro(self):
        """Being in Birch's lab should complete the intro."""
        from src.games.pokemon_gen3.intro_handler import IntroPhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 4)  # Birch's Lab
        handler.tick()
        assert handler.phase == IntroPhase.INTRO_COMPLETE
        assert handler.is_complete

    def test_house_1f_walks_down(self):
        """In house 1F, should walk down toward door."""
        handler, state, inp = self._make_handler()
        state._map_location = (1, 0)
        handler.tick()
        assert "Down" in inp.walks

    def test_heading_to_route_walks_up(self):
        """When heading to route, should walk north."""
        handler, state, inp = self._make_handler()
        # First visit rival house to set flag
        state._map_location = (1, 2)
        handler.tick()
        inp.walks.clear()
        # Then back in Littleroot
        state._map_location = (0, 9)
        handler.tick()
        assert "Up" in inp.walks


# ============================================================================
# ProgressionHandler Tests
# ============================================================================

class TestProgressionHandler:
    """Tests for the progression/phase detection handler."""

    def _make_handler(self):
        from src.games.pokemon_gen3.progression_handler import ProgressionHandler
        state = MockStateDetector()
        inp = MockInputController()
        handler = ProgressionHandler(state, inp)
        return handler, state, inp

    def test_intro_phase_no_pokemon(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 0)  # Player house
        state._party_count = 0
        phase = handler.detect_phase()
        assert phase == GamePhase.INTRO

    def test_littleroot_pre_starter(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)  # Littleroot
        state._party_count = 0
        phase = handler.detect_phase()
        assert phase == GamePhase.LITTLEROOT_PRE_STARTER

    def test_route_101_birch_no_pokemon(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)  # Route 101
        state._party_count = 0
        phase = handler.detect_phase()
        assert phase == GamePhase.ROUTE_101_BIRCH

    def test_post_battle_on_route_101(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)  # Route 101
        state._party_count = 1
        # No Pokedex flag
        phase = handler.detect_phase()
        assert phase == GamePhase.POST_BATTLE

    def test_return_to_lab_in_littleroot(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)  # Littleroot
        state._party_count = 1
        # No Pokedex flag
        phase = handler.detect_phase()
        assert phase == GamePhase.RETURN_TO_LAB

    def test_in_lab_with_pokemon(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (1, 4)  # Birch's Lab
        state._party_count = 1
        phase = handler.detect_phase()
        assert phase == GamePhase.IN_LAB

    def test_got_pokedex_in_littleroot(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)  # Littleroot
        state._party_count = 1
        state._event_flags[0x861] = True  # FLAG_SYS_POKEDEX_GET
        phase = handler.detect_phase()
        assert phase == GamePhase.GOT_POKEDEX

    def test_route_101_north_with_pokedex(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)  # Route 101
        state._party_count = 1
        state._event_flags[0x861] = True  # FLAG_SYS_POKEDEX_GET
        phase = handler.detect_phase()
        assert phase == GamePhase.ROUTE_101_NORTH

    def test_oldale_town(self):
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 10)  # Oldale
        state._party_count = 1
        state._event_flags[0x861] = True
        phase = handler.detect_phase()
        assert phase == GamePhase.OLDALE_TOWN

    def test_directive_walk_north_to_route(self):
        """Littleroot pre-starter should direct walking north."""
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)
        state._party_count = 0
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is not None
        assert directive.direction == "Up"

    def test_directive_walk_north_on_route_101(self):
        """Route 101 Birch phase should direct walking north."""
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)
        state._party_count = 0
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is not None
        assert directive.direction == "Up"

    def test_directive_walk_south_post_battle(self):
        """Post-battle should direct walking south to Littleroot."""
        handler, state, _ = self._make_handler()
        state._map_location = (0, 16)
        state._party_count = 1
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is not None
        assert directive.direction == "Down"

    def test_directive_none_in_lab(self):
        """In lab, no movement directive (dialogue handles it)."""
        handler, state, _ = self._make_handler()
        state._map_location = (1, 4)
        state._party_count = 1
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is None

    def test_directive_north_with_pokedex(self):
        """After getting Pokedex, head north."""
        handler, state, _ = self._make_handler()
        state._map_location = (0, 9)
        state._party_count = 1
        state._event_flags[0x861] = True
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is not None
        assert directive.direction == "Up"

    def test_directive_west_from_oldale(self):
        """From Oldale, head west to Route 102."""
        handler, state, _ = self._make_handler()
        state._map_location = (0, 10)
        state._party_count = 1
        state._event_flags[0x861] = True
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is not None
        assert directive.direction == "Left"

    def test_free_roam_no_directive(self):
        """Free roam should return no directive."""
        from src.games.pokemon_gen3.progression_handler import GamePhase
        handler, state, _ = self._make_handler()
        state._map_location = (0, 0)  # Petalburg
        state._party_count = 1
        state._event_flags[0x861] = True
        handler.detect_phase()
        directive = handler.get_directive()
        assert directive is None
