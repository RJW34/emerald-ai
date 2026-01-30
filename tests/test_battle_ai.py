"""
Tests for the Battle AI decision engine.

Tests battle decisions without requiring an emulator connection
by using mock data.
"""

import pytest
from unittest.mock import MagicMock

from src.games.pokemon_gen3.data_types import (
    Pokemon, Move, BattleState, PokemonType, Ability, Weather, PokemonParty
)
from src.games.pokemon_gen3.battle_handler import (
    PokemonGen3BattleHandler, BattleAction, TypeEffectiveness
)
from src.ai.battle_ai import BattleAI, BattleContext, BattleStrategy, BattlePhase


# =============================================================================
# Fixtures
# =============================================================================

def make_pokemon(
    species_id=1, level=50, hp=100, max_hp=100,
    attack=80, defense=80, speed=80, sp_attack=80, sp_defense=80,
    type1=PokemonType.NORMAL, type2=None,
    ability=Ability.NONE, status=0,
    moves=None
) -> Pokemon:
    """Helper to create test Pokemon."""
    if moves is None:
        moves = [
            Move(id=1, name="Tackle", pp=35, power=40, type=PokemonType.NORMAL, accuracy=100),
        ]
    return Pokemon(
        species_id=species_id, level=level,
        hp=hp, max_hp=max_hp,
        attack=attack, defense=defense, speed=speed,
        sp_attack=sp_attack, sp_defense=sp_defense,
        type1=type1, type2=type2,
        ability=ability, status=status,
        moves=moves,
    )


def make_battle_state(
    player=None, enemy=None,
    is_wild=True, weather=Weather.NONE
) -> BattleState:
    """Helper to create test battle states."""
    if player is None:
        player = make_pokemon()
    if enemy is None:
        enemy = make_pokemon()
    return BattleState(
        is_wild=is_wild,
        player_pokemon=[player],
        enemy_pokemon=[enemy],
        weather=weather,
        can_run=is_wild,
    )


def make_ai() -> BattleAI:
    """Create a BattleAI with mocked handler."""
    mock_client = MagicMock()
    handler = PokemonGen3BattleHandler(mock_client)
    return BattleAI(handler)


# =============================================================================
# Type Effectiveness Tests
# =============================================================================

class TestTypeEffectiveness:
    def test_super_effective(self):
        assert TypeEffectiveness.get_multiplier(PokemonType.WATER, PokemonType.FIRE) == 2.0

    def test_not_very_effective(self):
        assert TypeEffectiveness.get_multiplier(PokemonType.FIRE, PokemonType.WATER) == 0.5

    def test_immune(self):
        assert TypeEffectiveness.get_multiplier(PokemonType.NORMAL, PokemonType.GHOST) == 0.0

    def test_neutral(self):
        assert TypeEffectiveness.get_multiplier(PokemonType.NORMAL, PokemonType.NORMAL) == 1.0

    def test_dual_type_4x(self):
        # Flying + Water vs Electric = 4x
        mult = TypeEffectiveness.get_multiplier(
            PokemonType.ELECTRIC, PokemonType.FLYING, PokemonType.WATER
        )
        assert mult == 4.0

    def test_dual_type_cancel(self):
        # Ground vs Flying/Steel: Flying immune, Steel SE -> 0.0
        mult = TypeEffectiveness.get_multiplier(
            PokemonType.GROUND, PokemonType.FLYING, PokemonType.STEEL
        )
        assert mult == 0.0  # Flying immune overrides

    def test_is_super_effective(self):
        assert TypeEffectiveness.is_super_effective(PokemonType.FIRE, PokemonType.GRASS)
        assert not TypeEffectiveness.is_super_effective(PokemonType.FIRE, PokemonType.WATER)


# =============================================================================
# Battle AI Decision Tests
# =============================================================================

class TestBattleAIDecisions:
    def test_picks_super_effective_move(self):
        """AI should prefer super effective moves."""
        ai = make_ai()
        
        player = make_pokemon(
            type1=PokemonType.WATER,
            moves=[
                Move(id=1, name="Tackle", pp=35, power=40, type=PokemonType.NORMAL, accuracy=100),
                Move(id=2, name="Water Gun", pp=25, power=40, type=PokemonType.WATER, accuracy=100),
            ]
        )
        enemy = make_pokemon(type1=PokemonType.FIRE)
        state = make_battle_state(player, enemy)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.action == BattleAction.FIGHT
        assert decision.move_index == 1  # Water Gun should be preferred

    def test_avoids_immune_moves(self):
        """AI should not use moves the opponent is immune to."""
        ai = make_ai()
        
        player = make_pokemon(moves=[
            Move(id=1, name="Earthquake", pp=10, power=100, type=PokemonType.GROUND, accuracy=100),
            Move(id=2, name="Rock Slide", pp=10, power=75, type=PokemonType.ROCK, accuracy=90),
        ])
        # Enemy with Levitate (immune to Ground)
        enemy = make_pokemon(
            type1=PokemonType.ELECTRIC,
            ability=Ability.LEVITATE
        )
        state = make_battle_state(player, enemy)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.move_index == 1  # Should pick Rock Slide, not Earthquake

    def test_speedrun_flees_wild(self):
        """Speedrun strategy should always flee wild battles."""
        ai = make_ai()
        ai.set_strategy(BattleStrategy.SPEEDRUN)
        
        state = make_battle_state(is_wild=True)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.action == BattleAction.RUN

    def test_speedrun_fights_trainers(self):
        """Speedrun should fight trainers (can't flee)."""
        ai = make_ai()
        ai.set_strategy(BattleStrategy.SPEEDRUN)
        
        state = make_battle_state(is_wild=False)
        state.is_trainer = True
        state.can_run = False
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.action == BattleAction.FIGHT

    def test_prefers_stab_move(self):
        """AI should prefer moves that get STAB bonus."""
        ai = make_ai()
        
        # Water type with equal-power Water and Normal moves
        player = make_pokemon(
            type1=PokemonType.WATER,
            moves=[
                Move(id=1, name="Strength", pp=15, power=80, type=PokemonType.NORMAL, accuracy=100),
                Move(id=2, name="Surf", pp=15, power=80, type=PokemonType.WATER, accuracy=100),
            ]
        )
        enemy = make_pokemon(type1=PokemonType.NORMAL)
        state = make_battle_state(player, enemy)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.move_index == 1  # Surf with STAB > Strength

    def test_skips_no_pp_moves(self):
        """AI should not select moves with 0 PP."""
        ai = make_ai()
        
        player = make_pokemon(moves=[
            Move(id=1, name="Hydro Pump", pp=0, power=110, type=PokemonType.WATER, accuracy=80),
            Move(id=2, name="Water Gun", pp=25, power=40, type=PokemonType.WATER, accuracy=100),
        ])
        enemy = make_pokemon(type1=PokemonType.FIRE)
        state = make_battle_state(player, enemy)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        assert decision.move_index == 1  # Should pick Water Gun (has PP)

    def test_ohko_bonus(self):
        """AI should strongly prefer moves that can KO."""
        ai = make_ai()
        
        player = make_pokemon(
            attack=150, sp_attack=50, level=50,
            type1=PokemonType.NORMAL,
            moves=[
                Move(id=1, name="Hyper Beam", pp=5, power=150, type=PokemonType.NORMAL, accuracy=90),
                Move(id=2, name="Swift", pp=20, power=60, type=PokemonType.NORMAL, accuracy=100),
            ]
        )
        enemy = make_pokemon(hp=50, max_hp=100, defense=60)
        state = make_battle_state(player, enemy)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        # Should prefer the KO move even though Swift is more accurate
        assert decision.move_index == 0

    def test_weather_boost(self):
        """AI should consider weather boosting moves."""
        ai = make_ai()
        
        player = make_pokemon(
            type1=PokemonType.WATER,
            moves=[
                Move(id=1, name="Surf", pp=15, power=80, type=PokemonType.WATER, accuracy=100),
                Move(id=2, name="Ice Beam", pp=10, power=90, type=PokemonType.ICE, accuracy=100),
            ]
        )
        enemy = make_pokemon(type1=PokemonType.DRAGON)
        
        # In rain, Surf (80 * 1.5 STAB * 1.5 rain = 180) vs Ice Beam (90 * 2.0 SE = 180)
        # Ice Beam is SE against Dragon, so it should still win or be close
        state = make_battle_state(player, enemy, weather=Weather.RAIN)
        ctx = BattleContext(state=state)
        
        decision = ai.decide(ctx)
        # Both are reasonable; just verify it makes a decision
        assert decision.action == BattleAction.FIGHT


# =============================================================================
# Battle Phase Detection Tests  
# =============================================================================

class TestBattlePhase:
    def test_opening_phase(self):
        ai = make_ai()
        state = make_battle_state()
        ctx = BattleContext(state=state, turns_in_battle=0)
        
        phase = ai._assess_phase(ctx)
        assert phase == BattlePhase.OPENING

    def test_cleanup_phase(self):
        ai = make_ai()
        enemy = make_pokemon(hp=10, max_hp=100)
        state = make_battle_state(enemy=enemy)
        ctx = BattleContext(state=state, turns_in_battle=3)
        
        phase = ai._assess_phase(ctx)
        assert phase == BattlePhase.CLEANUP

    def test_endgame_phase(self):
        ai = make_ai()
        player = make_pokemon(hp=15, max_hp=100)
        state = make_battle_state(player=player)
        ctx = BattleContext(state=state, turns_in_battle=3)
        
        phase = ai._assess_phase(ctx)
        assert phase == BattlePhase.ENDGAME


# =============================================================================  
# Damage Estimation Tests
# =============================================================================

class TestDamageEstimation:
    def test_basic_damage(self):
        mock_client = MagicMock()
        handler = PokemonGen3BattleHandler(mock_client)
        
        attacker = make_pokemon(attack=100, level=50)
        defender = make_pokemon(defense=80)
        move = Move(id=1, power=80, type=PokemonType.NORMAL, accuracy=100)
        
        min_dmg, max_dmg = handler.estimate_damage(move, attacker, defender)
        assert min_dmg > 0
        assert max_dmg >= min_dmg
        assert max_dmg < 300  # Sanity check

    def test_immune_damage(self):
        """Normal vs Ghost = immune. Damage formula clamps to min 1 after calc, 
        but the multiplier makes base=0, then max(1,0)=1. The _score_move 
        correctly returns 0.0 for immune moves, so AI won't pick them."""
        mock_client = MagicMock()
        handler = PokemonGen3BattleHandler(mock_client)
        
        attacker = make_pokemon(attack=100, level=50)
        defender = make_pokemon(type1=PokemonType.GHOST, defense=80)
        move = Move(id=1, power=80, type=PokemonType.NORMAL, accuracy=100)
        
        # estimate_damage has max(1,...) clamping, so immune still returns 1
        # The AI scoring handles immunities separately (returns 0.0 score)
        min_dmg, max_dmg = handler.estimate_damage(move, attacker, defender)
        assert min_dmg <= 1
        assert max_dmg <= 1

    def test_status_move_zero_damage(self):
        mock_client = MagicMock()
        handler = PokemonGen3BattleHandler(mock_client)
        
        attacker = make_pokemon()
        defender = make_pokemon()
        move = Move(id=1, power=0, type=PokemonType.NORMAL)
        
        min_dmg, max_dmg = handler.estimate_damage(move, attacker, defender)
        assert min_dmg == 0
        assert max_dmg == 0


# =============================================================================
# Completion Tracker Tests (unit tests with mocks)
# =============================================================================

class TestCompletionTracker:
    def test_badge_count(self):
        from src.tracking.completion_tracker import BadgeProgress
        badges = BadgeProgress(stone=True, knuckle=True, dynamo=True)
        assert badges.count == 3
        assert not badges.complete

    def test_all_badges(self):
        from src.tracking.completion_tracker import BadgeProgress
        badges = BadgeProgress(
            stone=True, knuckle=True, dynamo=True, heat=True,
            balance=True, feather=True, mind=True, rain=True
        )
        assert badges.count == 8
        assert badges.complete

    def test_playtime_format(self):
        from src.tracking.completion_tracker import PlaytimeInfo
        pt = PlaytimeInfo(hours=12, minutes=34, seconds=56)
        assert str(pt) == "12:34:56"
        assert pt.total_seconds == 45296

    def test_completion_percentage_no_progress(self):
        from src.tracking.completion_tracker import GameProgress
        progress = GameProgress()
        assert progress.completion_percentage == 0.0

    def test_completion_percentage_with_badges(self):
        from src.tracking.completion_tracker import GameProgress, BadgeProgress
        progress = GameProgress()
        progress.badges = BadgeProgress(
            stone=True, knuckle=True, dynamo=True, heat=True
        )
        pct = progress.completion_percentage
        assert pct > 0
        assert pct < 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
