"""
Pokemon Generation 3 Data Types.

Data structures for representing Pokemon, moves, abilities, natures, and party
information as read from GBA game memory. Shared across all Gen 3 games.

Key differences from Gen 1:
- Abilities added (78 in Gen 3)
- Natures added (25 types with stat modifiers)
- Special split into Sp.Attack and Sp.Defense
- IVs are 0-31 (not 0-15 DVs)
- EVs are tracked per stat
- Contest stats added
- Steel and Dark types added
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class PokemonType(IntEnum):
    """Pokemon type IDs as stored in Gen 3 game memory."""

    NORMAL = 0
    FIGHTING = 1
    FLYING = 2
    POISON = 3
    GROUND = 4
    ROCK = 5
    BUG = 6
    GHOST = 7
    STEEL = 8
    MYSTERY = 9  # ??? type (used by Curse before Fairy was added)
    FIRE = 10
    WATER = 11
    GRASS = 12
    ELECTRIC = 13
    PSYCHIC = 14
    ICE = 15
    DRAGON = 16
    DARK = 17


class StatusCondition(IntEnum):
    """Status condition flags (Gen 3)."""

    NONE = 0
    SLEEP_MASK = 0x07  # Bits 0-2 indicate sleep turns remaining
    POISON = 0x08      # Bit 3
    BURN = 0x10        # Bit 4
    FREEZE = 0x20      # Bit 5
    PARALYSIS = 0x40   # Bit 6
    TOXIC = 0x80       # Bit 7 (bad poison)


class Nature(IntEnum):
    """
    Pokemon natures (25 total).

    Natures modify two stats by +10% and -10%.
    5 natures are neutral (same stat boosted and reduced).

    Formula: nature_id = personality_value % 25
    """

    # Neutral natures (no net stat change)
    HARDY = 0     # +Atk, -Atk
    DOCILE = 6    # +Def, -Def
    SERIOUS = 12  # +Spd, -Spd
    BASHFUL = 18  # +SpA, -SpA
    QUIRKY = 24   # +SpD, -SpD

    # +Attack natures
    LONELY = 1    # +Atk, -Def
    BRAVE = 2     # +Atk, -Spd
    ADAMANT = 3   # +Atk, -SpA
    NAUGHTY = 4   # +Atk, -SpD

    # +Defense natures
    BOLD = 5      # +Def, -Atk
    RELAXED = 7   # +Def, -Spd
    IMPISH = 8    # +Def, -SpA
    LAX = 9       # +Def, -SpD

    # +Speed natures
    TIMID = 10    # +Spd, -Atk
    HASTY = 11    # +Spd, -Def
    JOLLY = 13    # +Spd, -SpA
    NAIVE = 14    # +Spd, -SpD

    # +Special Attack natures
    MODEST = 15   # +SpA, -Atk
    MILD = 16     # +SpA, -Def
    QUIET = 17    # +SpA, -Spd
    RASH = 19     # +SpA, -SpD

    # +Special Defense natures
    CALM = 20     # +SpD, -Atk
    GENTLE = 21   # +SpD, -Def
    SASSY = 22    # +SpD, -Spd
    CAREFUL = 23  # +SpD, -SpA


# Nature stat modifier lookup tables
# Index 0=Atk, 1=Def, 2=Spd, 3=SpA, 4=SpD
NATURE_STAT_BOOST: dict[Nature, int] = {
    Nature.LONELY: 0, Nature.BRAVE: 0, Nature.ADAMANT: 0, Nature.NAUGHTY: 0,
    Nature.BOLD: 1, Nature.RELAXED: 1, Nature.IMPISH: 1, Nature.LAX: 1,
    Nature.TIMID: 2, Nature.HASTY: 2, Nature.JOLLY: 2, Nature.NAIVE: 2,
    Nature.MODEST: 3, Nature.MILD: 3, Nature.QUIET: 3, Nature.RASH: 3,
    Nature.CALM: 4, Nature.GENTLE: 4, Nature.SASSY: 4, Nature.CAREFUL: 4,
}

NATURE_STAT_REDUCE: dict[Nature, int] = {
    Nature.BOLD: 0, Nature.TIMID: 0, Nature.MODEST: 0, Nature.CALM: 0,
    Nature.LONELY: 1, Nature.HASTY: 1, Nature.MILD: 1, Nature.GENTLE: 1,
    Nature.BRAVE: 2, Nature.RELAXED: 2, Nature.QUIET: 2, Nature.SASSY: 2,
    Nature.ADAMANT: 3, Nature.IMPISH: 3, Nature.JOLLY: 3, Nature.CAREFUL: 3,
    Nature.NAUGHTY: 4, Nature.LAX: 4, Nature.NAIVE: 4, Nature.RASH: 4,
}


def get_nature_modifier(nature: Nature, stat_index: int) -> float:
    """
    Get the nature modifier for a specific stat.

    Args:
        nature: The Pokemon's nature
        stat_index: 0=Atk, 1=Def, 2=Spd, 3=SpA, 4=SpD

    Returns:
        1.1 for boosted stat, 0.9 for reduced stat, 1.0 for neutral
    """
    if nature in (Nature.HARDY, Nature.DOCILE, Nature.SERIOUS,
                  Nature.BASHFUL, Nature.QUIRKY):
        return 1.0

    if NATURE_STAT_BOOST.get(nature) == stat_index:
        return 1.1
    if NATURE_STAT_REDUCE.get(nature) == stat_index:
        return 0.9
    return 1.0


class Ability(IntEnum):
    """
    Pokemon abilities (Gen 3 has 78 abilities, IDs 1-77).

    Abilities affect battle mechanics, overworld behavior, or both.
    """

    NONE = 0
    STENCH = 1
    DRIZZLE = 2
    SPEED_BOOST = 3
    BATTLE_ARMOR = 4
    STURDY = 5
    DAMP = 6
    LIMBER = 7
    SAND_VEIL = 8
    STATIC = 9
    VOLT_ABSORB = 10
    WATER_ABSORB = 11
    OBLIVIOUS = 12
    CLOUD_NINE = 13
    COMPOUND_EYES = 14
    INSOMNIA = 15
    COLOR_CHANGE = 16
    IMMUNITY = 17
    FLASH_FIRE = 18
    SHIELD_DUST = 19
    OWN_TEMPO = 20
    SUCTION_CUPS = 21
    INTIMIDATE = 22
    SHADOW_TAG = 23
    ROUGH_SKIN = 24
    WONDER_GUARD = 25
    LEVITATE = 26
    EFFECT_SPORE = 27
    SYNCHRONIZE = 28
    CLEAR_BODY = 29
    NATURAL_CURE = 30
    LIGHTNING_ROD = 31
    SERENE_GRACE = 32
    SWIFT_SWIM = 33
    CHLOROPHYLL = 34
    ILLUMINATE = 35
    TRACE = 36
    HUGE_POWER = 37
    POISON_POINT = 38
    INNER_FOCUS = 39
    MAGMA_ARMOR = 40
    WATER_VEIL = 41
    MAGNET_PULL = 42
    SOUNDPROOF = 43
    RAIN_DISH = 44
    SAND_STREAM = 45
    PRESSURE = 46
    THICK_FAT = 47
    EARLY_BIRD = 48
    FLAME_BODY = 49
    RUN_AWAY = 50
    KEEN_EYE = 51
    HYPER_CUTTER = 52
    PICKUP = 53
    TRUANT = 54
    HUSTLE = 55
    CUTE_CHARM = 56
    PLUS = 57
    MINUS = 58
    FORECAST = 59
    STICKY_HOLD = 60
    SHED_SKIN = 61
    GUTS = 62
    MARVEL_SCALE = 63
    LIQUID_OOZE = 64
    OVERGROW = 65
    BLAZE = 66
    TORRENT = 67
    SWARM = 68
    ROCK_HEAD = 69
    DROUGHT = 70
    ARENA_TRAP = 71
    VITAL_SPIRIT = 72
    WHITE_SMOKE = 73
    PURE_POWER = 74
    SHELL_ARMOR = 75
    CACOPHONY = 76  # Unused, became Soundproof
    AIR_LOCK = 77


# Abilities that grant type immunities
ABILITY_TYPE_IMMUNITIES: dict[Ability, PokemonType] = {
    Ability.LEVITATE: PokemonType.GROUND,
    Ability.VOLT_ABSORB: PokemonType.ELECTRIC,
    Ability.WATER_ABSORB: PokemonType.WATER,
    Ability.FLASH_FIRE: PokemonType.FIRE,
    Ability.WONDER_GUARD: None,  # Special case: immune to non-super-effective
}

# Abilities that heal when hit by a type
ABILITY_TYPE_HEAL: dict[Ability, PokemonType] = {
    Ability.VOLT_ABSORB: PokemonType.ELECTRIC,
    Ability.WATER_ABSORB: PokemonType.WATER,
}

# Abilities that boost stats in weather
ABILITY_WEATHER_SPEED: dict[Ability, str] = {
    Ability.SWIFT_SWIM: "rain",
    Ability.CHLOROPHYLL: "sun",
    Ability.SAND_VEIL: "sandstorm",  # Evasion, not speed
}


class Weather(IntEnum):
    """Battle weather conditions."""

    NONE = 0
    RAIN = 1
    SANDSTORM = 2
    SUN = 3
    HAIL = 4


class ContestCategory(IntEnum):
    """Pokemon Contest categories."""

    COOL = 0
    BEAUTY = 1
    CUTE = 2
    SMART = 3
    TOUGH = 4


@dataclass
class Move:
    """
    A Pokemon move (Gen 3).

    Attributes:
        id: Move ID (1-354 in Gen 3)
        name: Move name (looked up from data)
        pp: Current PP remaining
        max_pp: Maximum PP
        type: Move type
        power: Base power (0 for status moves)
        accuracy: Accuracy percentage (0 for moves that can't miss)
        priority: Move priority (-7 to +5)
        is_contact: Whether the move makes contact
        category: Physical, Special, or Status
    """

    id: int
    name: str = ""
    pp: int = 0
    max_pp: int = 0
    type: Optional[PokemonType] = None
    power: int = 0
    accuracy: int = 100
    priority: int = 0
    is_contact: bool = False
    is_recoil: bool = False
    is_high_crit: bool = False
    target: str = "single"  # single, all_opponents, self, ally, etc.

    @property
    def is_damaging(self) -> bool:
        return self.power > 0

    @property
    def is_physical(self) -> bool:
        """Check if move is physical (Gen 3 uses type-based split)."""
        if self.type is None:
            return True
        # Physical types: Normal, Fighting, Flying, Poison, Ground, Rock, Bug, Ghost, Steel
        return self.type.value <= 8

    @property
    def is_special(self) -> bool:
        """Check if move is special (Gen 3 uses type-based split)."""
        if self.type is None:
            return False
        # Special types: Fire, Water, Grass, Electric, Psychic, Ice, Dragon, Dark
        return self.type.value >= 10


@dataclass
class Pokemon:
    """
    A Pokemon in the party or battle (Gen 3).

    Gen 3 additions over Gen 1:
    - Ability
    - Nature (affects stats)
    - Separate Sp.Attack and Sp.Defense
    - IVs (0-31 per stat)
    - EVs (0-255 per stat, 510 total)
    - Contest stats
    - Friendship/Happiness
    - Held item
    """

    species_id: int
    species_name: str = ""
    nickname: str = ""
    level: int = 1

    # HP
    hp: int = 0
    max_hp: int = 0

    # Status
    status: int = 0  # StatusCondition flags

    # Stats (Gen 3 has split Special)
    attack: int = 0
    defense: int = 0
    speed: int = 0
    sp_attack: int = 0
    sp_defense: int = 0

    # Gen 3 additions
    ability: Ability = Ability.NONE
    nature: Nature = Nature.HARDY
    held_item: int = 0
    friendship: int = 0

    # IVs (0-31 each)
    iv_hp: int = 0
    iv_attack: int = 0
    iv_defense: int = 0
    iv_speed: int = 0
    iv_sp_attack: int = 0
    iv_sp_defense: int = 0

    # EVs (0-255 each, 510 total max)
    ev_hp: int = 0
    ev_attack: int = 0
    ev_defense: int = 0
    ev_speed: int = 0
    ev_sp_attack: int = 0
    ev_sp_defense: int = 0

    # Contest stats (0-255 each)
    contest_cool: int = 0
    contest_beauty: int = 0
    contest_cute: int = 0
    contest_smart: int = 0
    contest_tough: int = 0
    contest_sheen: int = 0

    # Moves
    moves: list[Move] = field(default_factory=list)

    # Type(s)
    type1: Optional[PokemonType] = None
    type2: Optional[PokemonType] = None

    # Other
    experience: int = 0
    personality: int = 0  # 32-bit personality value
    ot_id: int = 0        # Original trainer ID
    is_egg: bool = False
    is_shiny: bool = False
    gender: int = 0       # 0=male, 1=female, 2=genderless
    pokerus: int = 0      # Pokerus status byte

    @property
    def is_fainted(self) -> bool:
        """Check if Pokemon has fainted (0 HP)."""
        return self.hp <= 0

    @property
    def hp_percentage(self) -> float:
        """Get HP as a percentage."""
        if self.max_hp <= 0:
            return 0.0
        return (self.hp / self.max_hp) * 100

    @property
    def is_poisoned(self) -> bool:
        return bool(self.status & StatusCondition.POISON)

    @property
    def is_badly_poisoned(self) -> bool:
        return bool(self.status & StatusCondition.TOXIC)

    @property
    def is_burned(self) -> bool:
        return bool(self.status & StatusCondition.BURN)

    @property
    def is_paralyzed(self) -> bool:
        return bool(self.status & StatusCondition.PARALYSIS)

    @property
    def is_frozen(self) -> bool:
        return bool(self.status & StatusCondition.FREEZE)

    @property
    def is_asleep(self) -> bool:
        return bool(self.status & StatusCondition.SLEEP_MASK)

    @property
    def has_status(self) -> bool:
        return self.status != StatusCondition.NONE

    @property
    def total_evs(self) -> int:
        """Get total EVs (max 510)."""
        return (self.ev_hp + self.ev_attack + self.ev_defense +
                self.ev_speed + self.ev_sp_attack + self.ev_sp_defense)

    def get_nature_modifier(self, stat: str) -> float:
        """
        Get nature modifier for a specific stat.

        Args:
            stat: One of 'attack', 'defense', 'speed', 'sp_attack', 'sp_defense'

        Returns:
            1.1, 1.0, or 0.9
        """
        stat_indices = {
            'attack': 0, 'defense': 1, 'speed': 2,
            'sp_attack': 3, 'sp_defense': 4
        }
        if stat not in stat_indices:
            return 1.0
        return get_nature_modifier(self.nature, stat_indices[stat])

    def get_effective_stat(self, stat: str) -> int:
        """Get stat value with nature modifier applied."""
        base_value = getattr(self, stat, 0)
        return int(base_value * self.get_nature_modifier(stat))

    def has_ability(self, ability: Ability) -> bool:
        """Check if Pokemon has a specific ability."""
        return self.ability == ability

    def is_immune_to_type(self, attack_type: PokemonType) -> bool:
        """Check if ability grants immunity to a type."""
        if self.ability in ABILITY_TYPE_IMMUNITIES:
            immune_type = ABILITY_TYPE_IMMUNITIES[self.ability]
            if immune_type == attack_type:
                return True
        return False

    def get_best_damaging_move(self) -> Optional[Move]:
        """Get the highest power move with PP remaining."""
        damaging_moves = [m for m in self.moves if m.is_damaging and m.pp > 0]
        if not damaging_moves:
            return None
        return max(damaging_moves, key=lambda m: m.power)

    def has_usable_moves(self) -> bool:
        """Check if any moves have PP remaining."""
        return any(m.pp > 0 for m in self.moves)


@dataclass
class PokemonParty:
    """
    The player's party of Pokemon.

    Attributes:
        pokemon: List of Pokemon in party (up to 6)
    """

    pokemon: list[Pokemon] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.pokemon)

    @property
    def lead(self) -> Optional[Pokemon]:
        """Get the first Pokemon in the party."""
        return self.pokemon[0] if self.pokemon else None

    @property
    def first_healthy(self) -> Optional[Pokemon]:
        """Get the first non-fainted Pokemon."""
        for mon in self.pokemon:
            if not mon.is_fainted:
                return mon
        return None

    @property
    def all_fainted(self) -> bool:
        """Check if all Pokemon have fainted (blackout)."""
        return all(mon.is_fainted for mon in self.pokemon)

    @property
    def healthy_count(self) -> int:
        """Count non-fainted Pokemon."""
        return sum(1 for mon in self.pokemon if not mon.is_fainted)

    def needs_healing(self, threshold: float = 50.0) -> bool:
        """Check if any Pokemon needs healing (below threshold %)."""
        return any(
            mon.hp_percentage < threshold
            for mon in self.pokemon
            if not mon.is_fainted
        )

    def get_pokemon_with_ability(self, ability: Ability) -> list[Pokemon]:
        """Get all Pokemon with a specific ability."""
        return [mon for mon in self.pokemon if mon.ability == ability]


@dataclass
class BattleState:
    """
    Current state of a battle (Gen 3).

    Supports both single and double battles.
    """

    is_wild: bool = True
    is_double: bool = False
    is_trainer: bool = False

    # Player's active Pokemon (1 for single, 2 for double)
    player_pokemon: list[Pokemon] = field(default_factory=list)

    # Enemy's active Pokemon (1 for single, 2 for double)
    enemy_pokemon: list[Pokemon] = field(default_factory=list)

    # Battle conditions
    weather: Weather = Weather.NONE
    weather_turns: int = 0
    can_run: bool = True
    turn_number: int = 1

    # Battle type flags
    is_safari: bool = False
    is_battle_tower: bool = False
    is_battle_frontier: bool = False

    @property
    def player_lead(self) -> Optional[Pokemon]:
        """Get player's first active Pokemon."""
        return self.player_pokemon[0] if self.player_pokemon else None

    @property
    def enemy_lead(self) -> Optional[Pokemon]:
        """Get enemy's first active Pokemon."""
        return self.enemy_pokemon[0] if self.enemy_pokemon else None

    @property
    def player_advantage(self) -> float:
        """
        Estimate player's advantage (positive = player favored).

        Simple heuristic based on HP percentages and speed.
        """
        if not self.player_pokemon or not self.enemy_pokemon:
            return 0.0

        player = self.player_lead
        enemy = self.enemy_lead

        if not player or not enemy:
            return 0.0

        player_hp_pct = player.hp_percentage
        enemy_hp_pct = enemy.hp_percentage

        # HP advantage
        hp_advantage = player_hp_pct - enemy_hp_pct

        # Speed advantage (who goes first)
        speed_advantage = 10 if player.speed > enemy.speed else -10

        return hp_advantage + speed_advantage

    def get_active_weather_boost(self, pokemon: Pokemon) -> float:
        """Get speed multiplier from weather-based abilities."""
        if self.weather == Weather.RAIN and pokemon.ability == Ability.SWIFT_SWIM:
            return 2.0
        if self.weather == Weather.SUN and pokemon.ability == Ability.CHLOROPHYLL:
            return 2.0
        return 1.0
