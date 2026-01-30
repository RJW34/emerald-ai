"""
Pokemon Generation 3 Battle Handler.

Handles battle decisions: move selection, switching, items, running.
Uses type effectiveness, abilities, natures, and damage calculation.
Supports both single and double battles.

Key differences from Gen 1:
- Abilities affect damage calculation and immunities
- Natures modify stats
- Double battles require target selection
- Steel and Dark types added
- Weather affects damage and abilities
- Physical/Special split is still type-based (not move-based)
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...emulator.bizhawk_client import BizHawkClient

from .memory_map import PokemonGen3Memory as Mem
from .data_types import (
    Pokemon, Move, BattleState, PokemonType, Ability, Nature, Weather,
    ABILITY_TYPE_IMMUNITIES, get_nature_modifier,
)
from ...data.move_data import enrich_move
from ...data.species_data import get_species_name

logger = logging.getLogger(__name__)


class BattleAction(Enum):
    """Actions that can be taken in battle."""

    FIGHT = auto()      # Use a move
    SWITCH = auto()     # Switch Pokemon
    BAG = auto()        # Use an item
    RUN = auto()        # Attempt to flee


@dataclass
class BattleDecision:
    """
    A decision to make in battle.

    For double battles, includes target selection.
    """

    action: BattleAction
    move_index: int = 0
    pokemon_index: int = 0
    item_id: int = 0
    target_index: int = 0  # For double battles: 0=enemy1, 1=enemy2, 2=ally
    reason: str = ""


class TypeEffectiveness:
    """
    Gen 3 type effectiveness chart.

    Includes Steel and Dark types, and fixes Gen 1 bugs.

    Multipliers:
    - 2.0: Super effective
    - 1.0: Normal effectiveness
    - 0.5: Not very effective
    - 0.0: No effect (immune)
    """

    # Type effectiveness matrix
    # CHART[attacking_type][defending_type] = multiplier
    CHART: dict[PokemonType, dict[PokemonType, float]] = {
        PokemonType.NORMAL: {
            PokemonType.ROCK: 0.5,
            PokemonType.STEEL: 0.5,
            PokemonType.GHOST: 0.0,
        },
        PokemonType.FIGHTING: {
            PokemonType.NORMAL: 2.0,
            PokemonType.ROCK: 2.0,
            PokemonType.STEEL: 2.0,
            PokemonType.ICE: 2.0,
            PokemonType.DARK: 2.0,
            PokemonType.FLYING: 0.5,
            PokemonType.POISON: 0.5,
            PokemonType.BUG: 0.5,
            PokemonType.PSYCHIC: 0.5,
            PokemonType.GHOST: 0.0,
        },
        PokemonType.FLYING: {
            PokemonType.FIGHTING: 2.0,
            PokemonType.BUG: 2.0,
            PokemonType.GRASS: 2.0,
            PokemonType.ROCK: 0.5,
            PokemonType.STEEL: 0.5,
            PokemonType.ELECTRIC: 0.5,
        },
        PokemonType.POISON: {
            PokemonType.GRASS: 2.0,
            PokemonType.POISON: 0.5,
            PokemonType.GROUND: 0.5,
            PokemonType.ROCK: 0.5,
            PokemonType.GHOST: 0.5,
            PokemonType.STEEL: 0.0,
        },
        PokemonType.GROUND: {
            PokemonType.POISON: 2.0,
            PokemonType.ROCK: 2.0,
            PokemonType.STEEL: 2.0,
            PokemonType.FIRE: 2.0,
            PokemonType.ELECTRIC: 2.0,
            PokemonType.BUG: 0.5,
            PokemonType.GRASS: 0.5,
            PokemonType.FLYING: 0.0,
        },
        PokemonType.ROCK: {
            PokemonType.FLYING: 2.0,
            PokemonType.BUG: 2.0,
            PokemonType.FIRE: 2.0,
            PokemonType.ICE: 2.0,
            PokemonType.FIGHTING: 0.5,
            PokemonType.GROUND: 0.5,
            PokemonType.STEEL: 0.5,
        },
        PokemonType.BUG: {
            PokemonType.GRASS: 2.0,
            PokemonType.PSYCHIC: 2.0,
            PokemonType.DARK: 2.0,
            PokemonType.FIGHTING: 0.5,
            PokemonType.FLYING: 0.5,
            PokemonType.POISON: 0.5,
            PokemonType.GHOST: 0.5,
            PokemonType.STEEL: 0.5,
            PokemonType.FIRE: 0.5,
        },
        PokemonType.GHOST: {
            PokemonType.GHOST: 2.0,
            PokemonType.PSYCHIC: 2.0,
            PokemonType.DARK: 0.5,
            PokemonType.STEEL: 0.5,
            PokemonType.NORMAL: 0.0,
        },
        PokemonType.STEEL: {
            PokemonType.ROCK: 2.0,
            PokemonType.ICE: 2.0,
            PokemonType.STEEL: 0.5,
            PokemonType.FIRE: 0.5,
            PokemonType.WATER: 0.5,
            PokemonType.ELECTRIC: 0.5,
        },
        PokemonType.FIRE: {
            PokemonType.BUG: 2.0,
            PokemonType.STEEL: 2.0,
            PokemonType.GRASS: 2.0,
            PokemonType.ICE: 2.0,
            PokemonType.ROCK: 0.5,
            PokemonType.FIRE: 0.5,
            PokemonType.WATER: 0.5,
            PokemonType.DRAGON: 0.5,
        },
        PokemonType.WATER: {
            PokemonType.GROUND: 2.0,
            PokemonType.ROCK: 2.0,
            PokemonType.FIRE: 2.0,
            PokemonType.WATER: 0.5,
            PokemonType.GRASS: 0.5,
            PokemonType.DRAGON: 0.5,
        },
        PokemonType.GRASS: {
            PokemonType.GROUND: 2.0,
            PokemonType.ROCK: 2.0,
            PokemonType.WATER: 2.0,
            PokemonType.FLYING: 0.5,
            PokemonType.POISON: 0.5,
            PokemonType.BUG: 0.5,
            PokemonType.STEEL: 0.5,
            PokemonType.FIRE: 0.5,
            PokemonType.GRASS: 0.5,
            PokemonType.DRAGON: 0.5,
        },
        PokemonType.ELECTRIC: {
            PokemonType.FLYING: 2.0,
            PokemonType.WATER: 2.0,
            PokemonType.GRASS: 0.5,
            PokemonType.ELECTRIC: 0.5,
            PokemonType.DRAGON: 0.5,
            PokemonType.GROUND: 0.0,
        },
        PokemonType.PSYCHIC: {
            PokemonType.FIGHTING: 2.0,
            PokemonType.POISON: 2.0,
            PokemonType.STEEL: 0.5,
            PokemonType.PSYCHIC: 0.5,
            PokemonType.DARK: 0.0,
        },
        PokemonType.ICE: {
            PokemonType.FLYING: 2.0,
            PokemonType.GROUND: 2.0,
            PokemonType.GRASS: 2.0,
            PokemonType.DRAGON: 2.0,
            PokemonType.STEEL: 0.5,
            PokemonType.FIRE: 0.5,
            PokemonType.WATER: 0.5,
            PokemonType.ICE: 0.5,
        },
        PokemonType.DRAGON: {
            PokemonType.DRAGON: 2.0,
            PokemonType.STEEL: 0.5,
        },
        PokemonType.DARK: {
            PokemonType.GHOST: 2.0,
            PokemonType.PSYCHIC: 2.0,
            PokemonType.FIGHTING: 0.5,
            PokemonType.DARK: 0.5,
            PokemonType.STEEL: 0.5,
        },
    }

    @classmethod
    def get_multiplier(
        cls,
        attack_type: PokemonType,
        defend_type1: PokemonType,
        defend_type2: Optional[PokemonType] = None
    ) -> float:
        """
        Get type effectiveness multiplier.

        Args:
            attack_type: Type of the attacking move
            defend_type1: Primary type of defender
            defend_type2: Secondary type of defender (optional)

        Returns:
            Effectiveness multiplier (0.0, 0.25, 0.5, 1.0, 2.0, or 4.0)
        """
        # Get base multiplier for type 1
        type_chart = cls.CHART.get(attack_type, {})
        mult1 = type_chart.get(defend_type1, 1.0)

        # If no second type, return first multiplier
        if defend_type2 is None or defend_type2 == defend_type1:
            return mult1

        # Multiply by second type effectiveness
        mult2 = type_chart.get(defend_type2, 1.0)
        return mult1 * mult2

    @classmethod
    def is_super_effective(
        cls,
        attack_type: PokemonType,
        defend_type1: PokemonType,
        defend_type2: Optional[PokemonType] = None
    ) -> bool:
        """Check if a move type is super effective."""
        return cls.get_multiplier(attack_type, defend_type1, defend_type2) > 1.0


class PokemonGen3BattleHandler:
    """
    Handles battle decisions in Pokemon Gen 3 games.

    Reads battle state from memory and determines optimal actions
    based on type effectiveness, abilities, natures, and strategy.

    Supports both single and double battles.
    """

    def __init__(self, client: "BizHawkClient"):
        """
        Initialize the battle handler.

        Args:
            client: BizHawkClient for memory access
        """
        self.client = client
        self._battle_state: Optional[BattleState] = None

    def read_battle_state(self) -> BattleState:
        """
        Read the current battle state from memory.

        Returns:
            BattleState with player and enemy Pokemon info
        """
        # Read battle flags
        battle_flags = self.client.read32(Mem.BATTLE_TYPE_FLAGS)

        is_double = bool(battle_flags & Mem.BATTLE_TYPE_DOUBLE)
        is_wild = bool(battle_flags & Mem.BATTLE_TYPE_WILD)
        is_trainer = bool(battle_flags & Mem.BATTLE_TYPE_TRAINER)
        is_safari = bool(battle_flags & Mem.BATTLE_TYPE_SAFARI)
        is_tower = bool(battle_flags & Mem.BATTLE_TYPE_BATTLE_TOWER)

        # Read player's Pokemon
        player_pokemon = [self._read_battle_pokemon(0)]
        if is_double:
            player2 = self._read_battle_pokemon(2)
            if player2:
                player_pokemon.append(player2)

        # Read enemy Pokemon
        enemy_pokemon = [self._read_battle_pokemon(1)]
        if is_double:
            enemy2 = self._read_battle_pokemon(3)
            if enemy2:
                enemy_pokemon.append(enemy2)

        # Read weather
        weather_val = self.client.read16(Mem.BATTLE_WEATHER)
        weather = Weather.NONE
        if weather_val & 0x07:  # Rain bits
            weather = Weather.RAIN
        elif weather_val & 0x18:  # Sandstorm bits
            weather = Weather.SANDSTORM
        elif weather_val & 0x60:  # Sun bits
            weather = Weather.SUN
        elif weather_val & 0x80:  # Hail bit
            weather = Weather.HAIL

        self._battle_state = BattleState(
            is_wild=is_wild,
            is_double=is_double,
            is_trainer=is_trainer,
            player_pokemon=[p for p in player_pokemon if p],
            enemy_pokemon=[p for p in enemy_pokemon if p],
            weather=weather,
            can_run=is_wild and not is_safari,
            is_safari=is_safari,
            is_battle_tower=is_tower,
        )

        return self._battle_state

    def _read_battle_pokemon(self, battler_index: int) -> Optional[Pokemon]:
        """
        Read a Pokemon's battle data.

        Args:
            battler_index: 0=player1, 1=enemy1, 2=player2, 3=enemy2
        """
        base_addr = Mem.BATTLE_MONS + (battler_index * Mem.BATTLE_MON_SIZE)

        try:
            species = self.client.read16(base_addr + Mem.BATTLE_MON_SPECIES_OFFSET)
            if species == 0:
                return None

            attack = self.client.read16(base_addr + Mem.BATTLE_MON_ATTACK_OFFSET)
            defense = self.client.read16(base_addr + Mem.BATTLE_MON_DEFENSE_OFFSET)
            speed = self.client.read16(base_addr + Mem.BATTLE_MON_SPEED_OFFSET)
            sp_attack = self.client.read16(base_addr + Mem.BATTLE_MON_SP_ATK_OFFSET)
            sp_defense = self.client.read16(base_addr + Mem.BATTLE_MON_SP_DEF_OFFSET)

            hp = self.client.read16(base_addr + Mem.BATTLE_MON_HP_OFFSET)
            max_hp = self.client.read16(base_addr + Mem.BATTLE_MON_MAX_HP_OFFSET)
            level = self.client.read8(base_addr + Mem.BATTLE_MON_LEVEL_OFFSET)
            status = self.client.read32(base_addr + Mem.BATTLE_MON_STATUS_OFFSET)

            ability_id = self.client.read8(base_addr + Mem.BATTLE_MON_ABILITY_OFFSET)
            type1 = self.client.read8(base_addr + Mem.BATTLE_MON_TYPE1_OFFSET)
            type2 = self.client.read8(base_addr + Mem.BATTLE_MON_TYPE2_OFFSET)

            # Read moves and enrich with database data
            moves = []
            for i in range(4):
                move_id = self.client.read16(
                    base_addr + Mem.BATTLE_MON_MOVES_OFFSET + (i * 2)
                )
                pp = self.client.read8(base_addr + Mem.BATTLE_MON_PP_OFFSET + i)
                if move_id != 0:
                    move = Move(id=move_id, pp=pp)
                    enrich_move(move)
                    moves.append(move)

            return Pokemon(
                species_id=species,
                species_name=get_species_name(species),
                level=level,
                hp=hp,
                max_hp=max_hp,
                status=status,
                attack=attack,
                defense=defense,
                speed=speed,
                sp_attack=sp_attack,
                sp_defense=sp_defense,
                ability=Ability(ability_id) if 0 < ability_id <= 77 else Ability.NONE,
                type1=PokemonType(type1) if type1 <= 17 else None,
                type2=PokemonType(type2) if type2 <= 17 and type2 != type1 else None,
                moves=moves,
            )

        except Exception as e:
            logger.error(f"Error reading battle Pokemon {battler_index}: {e}")
            return None

    def decide_action(
        self,
        strategy: str = "aggressive",
        allow_run: bool = True,
        target_pokemon: int = 0,
    ) -> BattleDecision:
        """
        Decide what action to take in battle.

        Args:
            strategy: Battle strategy
                - "aggressive": Use strongest moves, don't run
                - "safe": Prioritize survival, switch if needed
                - "speedrun": Run from wilds, optimal damage for trainers
                - "catch": Weaken for catching
            allow_run: Whether running is allowed by profile
            target_pokemon: Which enemy to target in double battles (0 or 1)

        Returns:
            BattleDecision with the chosen action
        """
        if self._battle_state is None:
            self.read_battle_state()

        state = self._battle_state

        # Strategy: Speedrun - always run from wild battles
        if strategy == "speedrun" and state.is_wild and allow_run and state.can_run:
            return BattleDecision(
                action=BattleAction.RUN,
                reason="Speedrun: flee from wild battle"
            )

        # Check if we should switch (low HP, bad matchup)
        if strategy == "safe" and self._should_switch():
            return self._decide_switch()

        # Default: Fight with best move
        return self._decide_fight(target_pokemon)

    def _decide_fight(self, target_index: int = 0) -> BattleDecision:
        """Decide which move to use."""
        state = self._battle_state
        player = state.player_lead
        enemy = state.enemy_pokemon[target_index] if target_index < len(state.enemy_pokemon) else state.enemy_lead

        if not player or not enemy:
            return BattleDecision(
                action=BattleAction.FIGHT,
                move_index=0,
                reason="No battle data, using first move"
            )

        # Find best move considering abilities
        best_move_idx = 0
        best_score = -1

        for i, move in enumerate(player.moves):
            if move.pp <= 0:
                continue

            score = self._score_move(move, player, enemy, state.weather)
            if score > best_score:
                best_score = score
                best_move_idx = i

        return BattleDecision(
            action=BattleAction.FIGHT,
            move_index=best_move_idx,
            target_index=target_index,
            reason=f"Best move (score: {best_score:.1f})"
        )

    def _score_move(
        self,
        move: Move,
        attacker: Pokemon,
        defender: Pokemon,
        weather: Weather = Weather.NONE
    ) -> float:
        """
        Score a move based on expected damage, considering abilities.

        Higher score = better move choice.
        """
        if move.power == 0:
            # Status moves get low priority for now
            return 10.0

        # Check ability immunities first
        if move.type is not None:
            if self._is_immune_by_ability(defender, move.type):
                return 0.0  # Move will fail

        # Base score from power
        score = float(move.power)

        # Apply type effectiveness if we have type data
        if move.type is not None and defender.type1 is not None:
            multiplier = TypeEffectiveness.get_multiplier(
                move.type, defender.type1, defender.type2
            )
            score *= multiplier

            # Check for Wonder Guard (only super-effective moves work)
            if defender.ability == Ability.WONDER_GUARD and multiplier <= 1.0:
                return 0.0

        # Apply STAB (Same Type Attack Bonus)
        if move.type is not None:
            if move.type == attacker.type1 or move.type == attacker.type2:
                score *= 1.5

        # Weather modifiers
        if weather == Weather.RAIN:
            if move.type == PokemonType.WATER:
                score *= 1.5
            elif move.type == PokemonType.FIRE:
                score *= 0.5
        elif weather == Weather.SUN:
            if move.type == PokemonType.FIRE:
                score *= 1.5
            elif move.type == PokemonType.WATER:
                score *= 0.5

        # Ability modifiers
        # Thick Fat reduces Fire/Ice damage
        if defender.ability == Ability.THICK_FAT:
            if move.type in (PokemonType.FIRE, PokemonType.ICE):
                score *= 0.5

        # Guts/Hustle boost attack
        if attacker.ability == Ability.GUTS and attacker.has_status:
            if move.is_physical:
                score *= 1.5
        if attacker.ability == Ability.HUGE_POWER or attacker.ability == Ability.PURE_POWER:
            if move.is_physical:
                score *= 2.0

        # Penalize for low accuracy
        if move.accuracy > 0 and move.accuracy < 100:
            score *= (move.accuracy / 100.0)

        return score

    def _is_immune_by_ability(self, defender: Pokemon, move_type: PokemonType) -> bool:
        """Check if defender's ability grants immunity to the move type."""
        if defender.ability == Ability.LEVITATE and move_type == PokemonType.GROUND:
            return True
        if defender.ability == Ability.VOLT_ABSORB and move_type == PokemonType.ELECTRIC:
            return True
        if defender.ability == Ability.WATER_ABSORB and move_type == PokemonType.WATER:
            return True
        if defender.ability == Ability.FLASH_FIRE and move_type == PokemonType.FIRE:
            return True
        if defender.ability == Ability.SOUNDPROOF:
            # Would need move data to check if sound-based
            pass
        return False

    def _should_switch(self) -> bool:
        """Check if we should switch Pokemon."""
        state = self._battle_state
        player = state.player_lead
        if not player:
            return False

        # Switch if HP is critical (< 20%)
        if player.hp_percentage < 20:
            return True

        # Check type matchup
        enemy = state.enemy_lead
        if enemy and player.type1:
            # If enemy has super effective STAB, consider switching
            for move in enemy.moves:
                if move.type and player.type1:
                    mult = TypeEffectiveness.get_multiplier(
                        move.type, player.type1, player.type2
                    )
                    if mult >= 2.0:
                        return True

        return False

    def _decide_switch(self) -> BattleDecision:
        """Decide which Pokemon to switch to."""
        # For now, just switch to next available
        # Would need party reading for smarter switching
        return BattleDecision(
            action=BattleAction.SWITCH,
            pokemon_index=1,
            reason="Switching due to low HP or bad matchup"
        )

    def estimate_damage(
        self,
        move: Move,
        attacker: Pokemon,
        defender: Pokemon,
        weather: Weather = Weather.NONE
    ) -> tuple[int, int]:
        """
        Estimate damage range for a move.

        Uses Gen 3 damage formula:
        Damage = ((2*Level/5 + 2) * Power * A/D / 50 + 2) * Modifiers

        Returns:
            (min_damage, max_damage) tuple
        """
        if move.power == 0:
            return (0, 0)

        # Check immunity first
        if move.type and self._is_immune_by_ability(defender, move.type):
            return (0, 0)

        level = attacker.level
        power = move.power

        # Determine if physical or special (Gen 3 type-based split)
        if move.is_physical:
            attack = attacker.attack
            defense = defender.defense
            # Ability modifiers for physical
            if attacker.ability in (Ability.HUGE_POWER, Ability.PURE_POWER):
                attack *= 2
            if attacker.ability == Ability.GUTS and attacker.has_status:
                attack = int(attack * 1.5)
            if attacker.ability == Ability.HUSTLE:
                attack = int(attack * 1.5)
        else:
            attack = attacker.sp_attack
            defense = defender.sp_defense

        # Thick Fat halves Fire/Ice damage
        if defender.ability == Ability.THICK_FAT:
            if move.type in (PokemonType.FIRE, PokemonType.ICE):
                attack = attack // 2

        # Marvel Scale boosts defense when statused
        if defender.ability == Ability.MARVEL_SCALE and defender.has_status:
            if move.is_physical:
                defense = int(defense * 1.5)

        # Base damage calculation
        if defense == 0:
            defense = 1  # Avoid division by zero
        base = ((2 * level // 5 + 2) * power * attack // defense) // 50 + 2

        # Weather modifiers
        if weather == Weather.RAIN:
            if move.type == PokemonType.WATER:
                base = int(base * 1.5)
            elif move.type == PokemonType.FIRE:
                base = base // 2
        elif weather == Weather.SUN:
            if move.type == PokemonType.FIRE:
                base = int(base * 1.5)
            elif move.type == PokemonType.WATER:
                base = base // 2

        # Type effectiveness
        if move.type is not None and defender.type1 is not None:
            multiplier = TypeEffectiveness.get_multiplier(
                move.type, defender.type1, defender.type2
            )
            # Wonder Guard check
            if defender.ability == Ability.WONDER_GUARD and multiplier <= 1.0:
                return (0, 0)
            base = int(base * multiplier)

        # STAB
        if move.type is not None:
            if move.type == attacker.type1 or move.type == attacker.type2:
                base = int(base * 1.5)

        # Burn halves physical attack damage
        if attacker.is_burned and move.is_physical:
            # Guts negates burn penalty
            if attacker.ability != Ability.GUTS:
                base = base // 2

        # Random factor (85% to 100%)
        min_damage = int(base * 0.85)
        max_damage = base

        return (max(1, min_damage), max(1, max_damage))

    def get_speed_order(self) -> list[tuple[int, Pokemon]]:
        """
        Get the order Pokemon will move in, considering abilities and weather.

        Returns:
            List of (battler_index, Pokemon) tuples in speed order
        """
        state = self._battle_state
        if not state:
            return []

        battlers = []

        # Add player Pokemon
        for i, mon in enumerate(state.player_pokemon):
            battlers.append((i * 2, mon))  # 0, 2

        # Add enemy Pokemon
        for i, mon in enumerate(state.enemy_pokemon):
            battlers.append((i * 2 + 1, mon))  # 1, 3

        # Calculate effective speeds
        def effective_speed(mon: Pokemon) -> float:
            speed = float(mon.speed)

            # Paralysis halves speed
            if mon.is_paralyzed:
                speed *= 0.25

            # Weather abilities
            if state.weather == Weather.RAIN and mon.ability == Ability.SWIFT_SWIM:
                speed *= 2.0
            elif state.weather == Weather.SUN and mon.ability == Ability.CHLOROPHYLL:
                speed *= 2.0
            elif state.weather == Weather.SANDSTORM and mon.ability == Ability.SAND_VEIL:
                pass  # Evasion boost, not speed

            return speed

        # Sort by effective speed (highest first)
        battlers.sort(key=lambda x: effective_speed(x[1]), reverse=True)

        return battlers


# =============================================================================
# Game-specific aliases
# =============================================================================

PokemonEmeraldBattleHandler = PokemonGen3BattleHandler
PokemonRubyBattleHandler = PokemonGen3BattleHandler
PokemonSapphireBattleHandler = PokemonGen3BattleHandler
PokemonFireRedBattleHandler = PokemonGen3BattleHandler
PokemonLeafGreenBattleHandler = PokemonGen3BattleHandler
