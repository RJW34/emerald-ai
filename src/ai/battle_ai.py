"""
Battle AI - Strategic decision engine for Pokemon battles.

Goes beyond simple type effectiveness to consider:
- Kill thresholds (can we OHKO/2HKO?)
- Speed tiers (who moves first?)
- Switch predictions
- HP management across the team
- Status move value (paralyze fast threats, toxic stall walls)
- Setup opportunities (stat boosts when safe)
- Catch logic (weaken then throw balls)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from ..games.pokemon_gen3.data_types import (
    Pokemon, Move, BattleState, PokemonType, Ability, Weather, PokemonParty
)
from ..games.pokemon_gen3.battle_handler import (
    PokemonGen3BattleHandler, BattleAction, BattleDecision, TypeEffectiveness
)

logger = logging.getLogger(__name__)


class BattleStrategy(Enum):
    """High-level battle strategies."""
    AGGRESSIVE = auto()    # KO as fast as possible
    SAFE = auto()          # Preserve HP, switch out of bad matchups
    CATCH = auto()         # Weaken then catch
    GRIND = auto()         # Fight wilds for XP, don't flee
    SPEEDRUN = auto()      # Flee wilds, fastest kills for trainers
    FRONTIER = auto()      # Battle Frontier: optimal play, no items


class BattlePhase(Enum):
    """What phase of battle we're in."""
    OPENING = auto()       # First turn, assess matchup
    MIDGAME = auto()       # Normal fighting
    ENDGAME = auto()       # Low HP, need to win or switch
    CLEANUP = auto()       # Enemy is low, finish them
    CATCHING = auto()      # Trying to catch


@dataclass
class BattleContext:
    """Extended battle context for AI decisions."""
    state: BattleState
    party: Optional[PokemonParty] = None
    phase: BattlePhase = BattlePhase.OPENING
    turns_in_battle: int = 0
    pokemon_caught_this_battle: bool = False
    balls_available: int = 0
    
    # Tracking
    damage_dealt_last_turn: int = 0
    damage_taken_last_turn: int = 0
    moves_used: list = field(default_factory=list)
    
    @property
    def player(self) -> Optional[Pokemon]:
        return self.state.player_lead
    
    @property
    def enemy(self) -> Optional[Pokemon]:
        return self.state.enemy_lead


class BattleAI:
    """
    Strategic battle AI that makes intelligent decisions.
    
    Architecture:
    1. Assess the situation (phase, matchup, resources)
    2. Generate candidate actions
    3. Score each candidate
    4. Pick the best one
    """
    
    def __init__(self, battle_handler: PokemonGen3BattleHandler):
        self.handler = battle_handler
        self.strategy = BattleStrategy.AGGRESSIVE
        self._context = None
        
        # Move database (populated from game data)
        # Maps move_id -> Move with full data
        self._move_db: dict[int, Move] = {}
    
    def set_strategy(self, strategy: BattleStrategy):
        """Set the current battle strategy."""
        self.strategy = strategy
        logger.info(f"Battle strategy set to: {strategy.name}")
    
    def decide(self, context: BattleContext) -> BattleDecision:
        """
        Make a battle decision given the current context.
        
        This is the main entry point for battle AI.
        """
        self._context = context
        
        # Update battle phase
        context.phase = self._assess_phase(context)
        
        # Strategy-specific overrides
        if self.strategy == BattleStrategy.SPEEDRUN:
            return self._decide_speedrun(context)
        elif self.strategy == BattleStrategy.CATCH:
            return self._decide_catch(context)
        
        # Generate and score candidates
        candidates = self._generate_candidates(context)
        
        if not candidates:
            # Fallback: use first move
            return BattleDecision(
                action=BattleAction.FIGHT,
                move_index=0,
                reason="No candidates generated, using first move"
            )
        
        # Sort by score, pick best
        candidates.sort(key=lambda c: c[1], reverse=True)
        best_decision, best_score = candidates[0]
        
        logger.info(
            f"Battle AI: {best_decision.action.name} "
            f"(score={best_score:.1f}, reason={best_decision.reason})"
        )
        
        return best_decision
    
    def _assess_phase(self, ctx: BattleContext) -> BattlePhase:
        """Determine what phase of battle we're in."""
        player = ctx.player
        enemy = ctx.enemy
        
        if not player or not enemy:
            return BattlePhase.OPENING
        
        if ctx.turns_in_battle == 0:
            return BattlePhase.OPENING
        
        # Catching phase
        if self.strategy == BattleStrategy.CATCH and ctx.state.is_wild:
            if enemy.hp_percentage <= 30:
                return BattlePhase.CATCHING
        
        # Cleanup: enemy is very low
        if enemy.hp_percentage <= 20:
            return BattlePhase.CLEANUP
        
        # Endgame: we're in trouble
        if player.hp_percentage <= 25:
            return BattlePhase.ENDGAME
        
        return BattlePhase.MIDGAME
    
    def _generate_candidates(self, ctx: BattleContext) -> list[tuple[BattleDecision, float]]:
        """Generate scored candidate actions."""
        candidates = []
        player = ctx.player
        enemy = ctx.enemy
        
        if not player or not enemy:
            return candidates
        
        # Score each move
        for i, move in enumerate(player.moves):
            if move.pp <= 0:
                continue
            
            score = self._score_move_advanced(move, player, enemy, ctx)
            decision = BattleDecision(
                action=BattleAction.FIGHT,
                move_index=i,
                reason=f"Move {move.name or move.id} score={score:.1f}"
            )
            candidates.append((decision, score))
        
        # Score switching
        if ctx.party and not ctx.state.is_battle_tower:
            switch_score, switch_idx = self._score_switch(ctx)
            if switch_score > 0:
                decision = BattleDecision(
                    action=BattleAction.SWITCH,
                    pokemon_index=switch_idx,
                    reason=f"Switch score={switch_score:.1f}"
                )
                candidates.append((decision, switch_score))
        
        # Score running (wild battles only)
        if ctx.state.is_wild and ctx.state.can_run:
            run_score = self._score_run(ctx)
            if run_score > 0:
                decision = BattleDecision(
                    action=BattleAction.RUN,
                    reason=f"Run score={run_score:.1f}"
                )
                candidates.append((decision, run_score))
        
        return candidates
    
    def _score_move_advanced(
        self, move: Move, player: Pokemon, enemy: Pokemon, ctx: BattleContext
    ) -> float:
        """
        Advanced move scoring considering game context.
        
        Factors:
        - Base damage/effectiveness (from battle_handler)
        - Kill probability (OHKO bonus)
        - Speed advantage (going first matters)
        - Status value
        - Setup value (stat boosts)
        - PP conservation
        """
        # Start with basic damage score from handler
        base_score = self.handler._score_move(
            move, player, enemy, ctx.state.weather
        )
        
        score = base_score
        
        # === Kill threshold bonus ===
        min_dmg, max_dmg = self.handler.estimate_damage(
            move, player, enemy, ctx.state.weather
        )
        
        if max_dmg > 0 and enemy.hp > 0:
            # Can we OHKO?
            if min_dmg >= enemy.hp:
                score += 200  # Guaranteed KO is huge
            elif max_dmg >= enemy.hp:
                score += 100  # Possible KO
            # Can we 2HKO? (relevant if we outspeed)
            elif min_dmg * 2 >= enemy.hp and player.speed > enemy.speed:
                score += 50
        
        # === Speed consideration ===
        we_outspeed = player.speed > enemy.speed
        
        # If we don't outspeed and might die, prioritize KO moves and priority
        if not we_outspeed:
            # Estimate enemy's best damage against us
            enemy_threat = self._estimate_enemy_threat(enemy, player, ctx)
            
            if enemy_threat >= player.hp:
                # We might die next turn! Priority moves are critical
                if move.priority > 0:
                    score += 150
                # Guaranteed KO saves us even if we're slower
                if min_dmg >= enemy.hp:
                    score += 100
                # Possible KO still worth trying
                elif max_dmg >= enemy.hp:
                    score += 50
            
            # Even if not dying, priority moves matter when outsped
            if ctx.phase == BattlePhase.ENDGAME and move.priority > 0:
                score += 80
        
        # === Status move scoring ===
        if move.power == 0:
            score = self._score_status_move(move, player, enemy, ctx)
        
        # === PP conservation ===
        # Penalize using high-PP moves when low-PP moves would work
        if move.pp <= 2:
            score -= 20  # Conserve last PP
        
        # === Phase adjustments ===
        if ctx.phase == BattlePhase.CLEANUP:
            # Just finish them off - prefer reliable moves
            if move.accuracy >= 100 and move.power > 0:
                score += 30
        
        if ctx.phase == BattlePhase.OPENING:
            # Consider setup moves more on turn 1
            if move.power == 0:
                score += 15
        
        return score
    
    def _estimate_enemy_threat(
        self, enemy: Pokemon, player: Pokemon, ctx: BattleContext
    ) -> int:
        """Estimate the max damage the enemy could deal to us this turn."""
        max_threat = 0
        for move in enemy.moves:
            if move.pp <= 0 or move.power == 0:
                continue
            _, max_dmg = self.handler.estimate_damage(
                move, enemy, player, ctx.state.weather
            )
            if max_dmg > max_threat:
                max_threat = max_dmg
        return max_threat
    
    def _score_status_move(
        self, move: Move, player: Pokemon, enemy: Pokemon, ctx: BattleContext
    ) -> float:
        """Score a status/support move."""
        # Base: low priority
        score = 5.0
        
        # Don't use status moves in cleanup phase
        if ctx.phase == BattlePhase.CLEANUP:
            return 0.0
        
        # If enemy is already statused, don't try to status again
        if enemy.has_status:
            return 2.0
        
        # Status moves are only worth it against tough enemies
        # Don't waste turns debuffing a Lv2 Poochyena
        level_diff = enemy.level - player.level
        if level_diff < -5:
            return 3.0  # Enemy is much weaker, just attack
        
        # Status moves are better early in battle against real threats
        if ctx.turns_in_battle <= 2 and level_diff >= -2:
            score += 15
        
        # Higher value against tanky enemies
        if enemy.hp_percentage > 80 and enemy.max_hp > player.max_hp * 0.5:
            score += 10
        
        return score
    
    def _score_switch(self, ctx: BattleContext) -> tuple[float, int]:
        """Score switching and find best switch target."""
        player = ctx.player
        enemy = ctx.enemy
        
        if not player or not enemy or not ctx.party:
            return (0.0, 0)
        
        best_score = 0.0
        best_idx = 0
        
        for i, mon in enumerate(ctx.party.pokemon):
            if mon.is_fainted or mon == player:
                continue
            
            score = 0.0
            
            # Type advantage
            if mon.type1 and enemy.type1:
                # Check if we resist enemy's likely attacks
                # Check if we have super effective STAB
                for move in mon.moves:
                    if move.type and move.power > 0:
                        mult = TypeEffectiveness.get_multiplier(
                            move.type, enemy.type1, enemy.type2
                        )
                        if mult > 1.0:
                            score += 30
                            # STAB bonus
                            if move.type == mon.type1 or move.type == mon.type2:
                                score += 15
            
            # HP consideration
            score += mon.hp_percentage * 0.5
            
            # Speed advantage
            if mon.speed > enemy.speed:
                score += 10
            
            if score > best_score:
                best_score = score
                best_idx = i
        
        # Only recommend switch if significantly better than staying in
        # Account for losing a turn to switch
        switch_threshold = 50.0
        
        # Lower threshold if current Pokemon is in danger
        if player.hp_percentage < 20:
            switch_threshold = 20.0
        elif player.hp_percentage < 40:
            switch_threshold = 35.0
        
        # If enemy outspeeds and can KO us, switching is more urgent
        enemy_threat = self._estimate_enemy_threat(enemy, player, ctx)
        if enemy_threat >= player.hp and player.speed < enemy.speed:
            switch_threshold = 15.0
            # Boost the best switch candidate
            best_score += 30
        
        if best_score > switch_threshold:
            return (best_score, best_idx)
        
        return (0.0, 0)
    
    def _score_run(self, ctx: BattleContext) -> float:
        """Score fleeing from battle."""
        if self.strategy == BattleStrategy.SPEEDRUN:
            return 500.0  # Always flee in speedrun
        
        if self.strategy == BattleStrategy.GRIND:
            return 0.0  # Never flee when grinding
        
        if self.strategy == BattleStrategy.CATCH:
            return 0.0  # Don't flee when trying to catch
        
        # Otherwise, flee if in danger and not worth fighting
        player = ctx.player
        if player and player.hp_percentage < 20:
            return 80.0  # Flee if low HP
        
        return 0.0
    
    def _decide_speedrun(self, ctx: BattleContext) -> BattleDecision:
        """Speedrun: flee wilds, OHKO trainers."""
        if ctx.state.is_wild and ctx.state.can_run:
            return BattleDecision(
                action=BattleAction.RUN,
                reason="Speedrun: flee wild battle"
            )
        
        # For trainers, use strongest move
        candidates = self._generate_candidates(ctx)
        fight_candidates = [c for c in candidates if c[0].action == BattleAction.FIGHT]
        
        if fight_candidates:
            fight_candidates.sort(key=lambda c: c[1], reverse=True)
            return fight_candidates[0][0]
        
        return BattleDecision(
            action=BattleAction.FIGHT,
            move_index=0,
            reason="Speedrun fallback"
        )
    
    def _decide_catch(self, ctx: BattleContext) -> BattleDecision:
        """Catch strategy: weaken then throw balls."""
        enemy = ctx.enemy
        
        if not enemy:
            return BattleDecision(
                action=BattleAction.FIGHT,
                move_index=0,
                reason="No enemy data"
            )
        
        # If HP is low enough, try to catch
        if enemy.hp_percentage <= 30:
            # TODO: Implement item usage for Poke Balls
            # For now, keep attacking gently
            pass
        
        # If HP is too high, use weakest effective move
        if enemy.hp_percentage > 30:
            player = ctx.player
            if player:
                # Find weakest damaging move that won't KO
                weakest_score = float('inf')
                weakest_idx = 0
                
                for i, move in enumerate(player.moves):
                    if move.pp <= 0 or move.power == 0:
                        continue
                    
                    _, max_dmg = self.handler.estimate_damage(
                        move, player, enemy, ctx.state.weather
                    )
                    
                    # Want to damage but not KO
                    if 0 < max_dmg < enemy.hp:
                        if max_dmg < weakest_score:
                            weakest_score = max_dmg
                            weakest_idx = i
                
                return BattleDecision(
                    action=BattleAction.FIGHT,
                    move_index=weakest_idx,
                    reason=f"Weakening for catch (est dmg: {weakest_score})"
                )
        
        # Status moves are great for catching
        player = ctx.player
        if player and not enemy.has_status:
            for i, move in enumerate(player.moves):
                if move.pp > 0 and move.power == 0:
                    # TODO: Check if it's a status-inflicting move
                    return BattleDecision(
                        action=BattleAction.FIGHT,
                        move_index=i,
                        reason="Status move for catching"
                    )
        
        return BattleDecision(
            action=BattleAction.FIGHT,
            move_index=0,
            reason="Catch: default attack"
        )
