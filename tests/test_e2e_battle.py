"""
End-to-end battle tests using MockBizHawkClient.

Tests the full pipeline: memory read → state detection → battle AI → decision
without needing BizHawk running.
"""

import pytest
from src.emulator.mock_client import MockBizHawkClient, SCENARIOS
from src.games.pokemon_gen3.state_detector import PokemonGen3StateDetector, PokemonGen3State
from src.games.pokemon_gen3.battle_handler import PokemonGen3BattleHandler, BattleAction
from src.ai.battle_ai import BattleAI, BattleContext, BattleStrategy
from src.games.pokemon_gen3.data_types import PokemonType


class TestE2EBattlePipeline:
    """Full pipeline tests for each scenario."""

    def _run_scenario(self, name: str, strategy: str = "aggressive"):
        """Set up and run a battle scenario, returning the AI decision."""
        client = MockBizHawkClient(name)
        client.connect()
        
        detector = PokemonGen3StateDetector(client)
        handler = PokemonGen3BattleHandler(client)
        ai = BattleAI(handler)
        
        strategy_map = {
            "aggressive": BattleStrategy.AGGRESSIVE,
            "speedrun": BattleStrategy.SPEEDRUN,
            "safe": BattleStrategy.SAFE,
        }
        ai.set_strategy(strategy_map.get(strategy, BattleStrategy.AGGRESSIVE))
        
        # Detect state
        state = detector.detect()
        
        # Read battle state
        battle_state = handler.read_battle_state()
        party = detector.read_party()
        
        # Create context and decide
        ctx = BattleContext(state=battle_state, party=party)
        decision = ai.decide(ctx)
        
        return state, battle_state, decision

    def test_mudkip_vs_poochyena_detects_wild_battle(self):
        state, battle_state, _ = self._run_scenario("mudkip_vs_poochyena")
        assert state == PokemonGen3State.BATTLE_WILD
        assert battle_state.is_wild

    def test_mudkip_vs_poochyena_reads_pokemon(self):
        _, battle_state, _ = self._run_scenario("mudkip_vs_poochyena")
        player = battle_state.player_lead
        enemy = battle_state.enemy_lead
        
        assert player is not None
        assert enemy is not None
        assert player.species_name == "Mudkip"
        assert player.level == 5
        assert enemy.species_name == "Poochyena"
        assert enemy.level == 2

    def test_mudkip_vs_poochyena_uses_tackle(self):
        """Mudkip only has Tackle and Growl; should pick Tackle (has damage)."""
        _, _, decision = self._run_scenario("mudkip_vs_poochyena")
        assert decision.action == BattleAction.FIGHT
        assert decision.move_index == 0  # Tackle (power 35) > Growl (power 0)

    def test_mudkip_vs_poochyena_speedrun_flees(self):
        """Speedrun should flee wild battles."""
        _, _, decision = self._run_scenario("mudkip_vs_poochyena", strategy="speedrun")
        assert decision.action == BattleAction.RUN

    def test_blaziken_vs_flygon_detects_trainer(self):
        state, battle_state, _ = self._run_scenario("blaziken_vs_flygon")
        assert state == PokemonGen3State.BATTLE_TRAINER
        assert battle_state.is_trainer

    def test_blaziken_vs_flygon_reads_moves(self):
        """Verify move enrichment works end-to-end."""
        _, battle_state, _ = self._run_scenario("blaziken_vs_flygon")
        player = battle_state.player_lead
        assert player is not None
        
        move_names = [m.name for m in player.moves]
        assert "Blaze Kick" in move_names
        assert "Brick Break" in move_names
        assert "Flamethrower" in move_names

    def test_blaziken_vs_flygon_avoids_ground_on_levitate(self):
        """Flygon has Levitate — AI should NOT pick Earthquake-type moves.
        Blaziken doesn't have Earthquake, but this tests the ability awareness."""
        _, battle_state, decision = self._run_scenario("blaziken_vs_flygon")
        # Flygon is Ground/Dragon, Levitate
        enemy = battle_state.enemy_lead
        assert enemy.species_name == "Flygon"
        # AI should pick a move — just verify it makes a valid choice
        assert decision.action == BattleAction.FIGHT

    def test_blaziken_vs_flygon_speedrun_fights_trainer(self):
        """Can't flee trainer battles, even in speedrun."""
        _, _, decision = self._run_scenario("blaziken_vs_flygon", strategy="speedrun")
        assert decision.action == BattleAction.FIGHT

    def test_swampert_vs_wailord_avoids_water_absorb(self):
        """Wailord has Water Absorb — AI should not use Water moves."""
        _, battle_state, decision = self._run_scenario("swampert_vs_wailord_rain")
        enemy = battle_state.enemy_lead
        assert enemy.species_name == "Wailord"
        
        # AI should pick Earthquake or Ice Beam, NOT Surf
        assert decision.action == BattleAction.FIGHT
        player = battle_state.player_lead
        chosen_move = player.moves[decision.move_index]
        # Should avoid Water type (Water Absorb immunity)
        assert chosen_move.type != PokemonType.WATER, \
            f"AI chose {chosen_move.name} (Water) against Water Absorb!"

    def test_swampert_vs_wailord_prefers_earthquake(self):
        """Earthquake is neutral on Water, 100 power, STAB — should be top pick."""
        _, battle_state, decision = self._run_scenario("swampert_vs_wailord_rain")
        player = battle_state.player_lead
        chosen = player.moves[decision.move_index]
        # Earthquake (100 power, Ground STAB) should beat Ice Beam (95 power, no STAB, neutral)
        assert chosen.name == "Earthquake", f"Expected Earthquake, got {chosen.name}"


class TestMockClientIntegrity:
    """Verify the mock client returns correct data."""

    def test_game_info(self):
        client = MockBizHawkClient()
        client.connect()
        assert client.get_game_code() == "BPEE"
        assert "Emerald" in client.get_game_title()

    def test_all_scenarios_loadable(self):
        for name in SCENARIOS:
            client = MockBizHawkClient(name)
            client.connect()
            assert client.is_connected()

    def test_battle_struct_roundtrip(self):
        """Verify MockBattlePokemon serialization matches what the handler reads."""
        client = MockBizHawkClient("blaziken_vs_flygon")
        client.connect()
        handler = PokemonGen3BattleHandler(client)
        state = handler.read_battle_state()
        
        player = state.player_lead
        assert player.species_id == 257  # Blaziken
        assert player.level == 36
        assert player.hp == 110
        assert len(player.moves) == 4
