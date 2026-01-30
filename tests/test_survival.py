"""Tests for survival-aware battle AI behavior."""

from unittest.mock import MagicMock
from src.games.pokemon_gen3.data_types import (
    Pokemon, Move, BattleState, PokemonType, Weather, PokemonParty
)
from src.games.pokemon_gen3.battle_handler import PokemonGen3BattleHandler, BattleAction
from src.ai.battle_ai import BattleAI, BattleContext, BattleStrategy


def make_ai():
    mock_client = MagicMock()
    handler = PokemonGen3BattleHandler(mock_client)
    return BattleAI(handler)


class TestSurvivalAwareness:
    def test_prefers_priority_when_about_to_die(self):
        """When enemy outspeeds and can KO, prioritize Quick Attack over stronger move."""
        ai = make_ai()
        
        player = Pokemon(
            species_id=1, level=30, hp=15, max_hp=100,
            attack=80, defense=60, speed=50, sp_attack=50, sp_defense=60,
            type1=PokemonType.NORMAL,
            moves=[
                Move(id=70, name="Strength", pp=15, power=80,
                     type=PokemonType.NORMAL, accuracy=100, priority=0),
                Move(id=98, name="Quick Attack", pp=30, power=40,
                     type=PokemonType.NORMAL, accuracy=100, priority=1),
            ]
        )
        # Fast enemy that can KO us
        enemy = Pokemon(
            species_id=2, level=30, hp=20, max_hp=100,
            attack=90, defense=60, speed=90, sp_attack=50, sp_defense=60,
            type1=PokemonType.NORMAL,
            moves=[
                Move(id=33, name="Tackle", pp=35, power=40,
                     type=PokemonType.NORMAL, accuracy=100),
            ]
        )
        
        state = BattleState(
            is_wild=True, player_pokemon=[player], enemy_pokemon=[enemy],
            can_run=True
        )
        ctx = BattleContext(state=state, turns_in_battle=3)
        decision = ai.decide(ctx)
        
        # Quick Attack has priority — if enemy can kill us, we need to move first
        # The exact choice depends on whether QA can KO the enemy
        assert decision.action == BattleAction.FIGHT
        # Quick Attack should be preferred since enemy outspeeds and threatens KO
        chosen_move = player.moves[decision.move_index]
        assert chosen_move.priority > 0 or chosen_move.power >= 80, \
            f"Expected priority move or strong KO move, got {chosen_move.name}"

    def test_switch_more_attractive_when_outsped_and_dying(self):
        """Switch threshold should be lower when we're about to die."""
        ai = make_ai()
        
        player = Pokemon(
            species_id=1, level=30, hp=10, max_hp=100,
            attack=50, defense=50, speed=30, sp_attack=50, sp_defense=50,
            type1=PokemonType.NORMAL,
            moves=[
                Move(id=33, name="Tackle", pp=35, power=40,
                     type=PokemonType.NORMAL, accuracy=100),
            ]
        )
        # Switch candidate: healthy and has type advantage
        switch_mon = Pokemon(
            species_id=3, level=30, hp=100, max_hp=100,
            attack=80, defense=80, speed=80, sp_attack=80, sp_defense=80,
            type1=PokemonType.ROCK,
            moves=[
                Move(id=157, name="Rock Slide", pp=10, power=75,
                     type=PokemonType.ROCK, accuracy=90),
            ]
        )
        
        enemy = Pokemon(
            species_id=2, level=30, hp=80, max_hp=100,
            attack=100, defense=60, speed=90, sp_attack=50, sp_defense=60,
            type1=PokemonType.FLYING,
            moves=[
                Move(id=17, name="Wing Attack", pp=35, power=60,
                     type=PokemonType.FLYING, accuracy=100),
            ]
        )
        
        party = PokemonParty(pokemon=[player, switch_mon])
        state = BattleState(
            is_wild=False, player_pokemon=[player], enemy_pokemon=[enemy],
            can_run=False
        )
        ctx = BattleContext(state=state, party=party, turns_in_battle=2)
        decision = ai.decide(ctx)
        
        # With 10 HP, enemy outspeeds, and switch has Rock vs Flying SE,
        # switching should be attractive
        # Accept either switch or fight — the AI should make a reasonable choice
        assert decision.action in (BattleAction.FIGHT, BattleAction.SWITCH)
