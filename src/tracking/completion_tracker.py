"""
Game Completion Tracker for Pokemon Emerald.

Tracks progress toward 100% completion by reading event flags,
badges, Pokedex, items, and other game state from memory.

Outputs a structured progress report that can be saved to disk
and displayed on stream.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector

from ..games.pokemon_gen3.memory_map import PokemonGen3Memory as Mem

logger = logging.getLogger(__name__)


@dataclass
class BadgeProgress:
    """Badge collection progress."""
    stone: bool = False       # Roxanne
    knuckle: bool = False     # Brawly
    dynamo: bool = False      # Wattson
    heat: bool = False        # Flannery
    balance: bool = False     # Norman
    feather: bool = False     # Winona
    mind: bool = False        # Tate & Liza
    rain: bool = False        # Wallace
    
    @property
    def count(self) -> int:
        return sum([
            self.stone, self.knuckle, self.dynamo, self.heat,
            self.balance, self.feather, self.mind, self.rain
        ])
    
    @property
    def total(self) -> int:
        return 8
    
    @property
    def complete(self) -> bool:
        return self.count == self.total


@dataclass
class StoryProgress:
    """Main story progression flags."""
    has_starter: bool = False
    has_pokedex: bool = False
    has_pokenav: bool = False
    clock_set: bool = False
    elite_four_cleared: bool = False
    
    # Legendary encounters
    rayquaza_caught: bool = False
    groudon_caught: bool = False
    kyogre_caught: bool = False
    regirock_caught: bool = False
    regice_caught: bool = False
    registeel_caught: bool = False
    latias_caught: bool = False
    latios_caught: bool = False


@dataclass 
class PokedexProgress:
    """Pokedex completion tracking."""
    seen: int = 0
    caught: int = 0
    # Emerald has ~202 Pokemon obtainable without trading
    target_caught: int = 202
    
    @property
    def seen_percentage(self) -> float:
        return (self.seen / 386) * 100 if self.seen > 0 else 0.0
    
    @property
    def caught_percentage(self) -> float:
        return (self.caught / self.target_caught) * 100 if self.caught > 0 else 0.0


@dataclass
class PartySnapshot:
    """Snapshot of party state."""
    count: int = 0
    total_levels: int = 0
    highest_level: int = 0
    all_healthy: bool = True
    
    @property
    def average_level(self) -> float:
        return self.total_levels / self.count if self.count > 0 else 0.0


@dataclass
class PlaytimeInfo:
    """Play time tracking."""
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    
    @property
    def total_seconds(self) -> int:
        return self.hours * 3600 + self.minutes * 60 + self.seconds
    
    def __str__(self) -> str:
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"


@dataclass
class GameProgress:
    """Complete game progress snapshot."""
    timestamp: float = 0.0
    badges: BadgeProgress = field(default_factory=BadgeProgress)
    story: StoryProgress = field(default_factory=StoryProgress)
    pokedex: PokedexProgress = field(default_factory=PokedexProgress)
    party: PartySnapshot = field(default_factory=PartySnapshot)
    playtime: PlaytimeInfo = field(default_factory=PlaytimeInfo)
    
    # Map location
    map_group: int = 0
    map_num: int = 0
    player_x: int = 0
    player_y: int = 0
    
    # Overall completion estimate
    @property
    def completion_percentage(self) -> float:
        """Estimate overall completion percentage."""
        weights = {
            'badges': (self.badges.count / 8) * 20,          # 20% weight
            'story': self._story_score() * 25,                 # 25% weight
            'pokedex': (self.pokedex.caught / 202) * 30,      # 30% weight
            'frontier': 0,                                      # 25% weight (TODO)
        }
        return min(100.0, sum(weights.values()))
    
    def _story_score(self) -> float:
        """Score story completion 0.0 - 1.0."""
        flags = [
            self.story.has_starter,
            self.story.has_pokedex,
            self.story.has_pokenav,
            self.badges.count >= 4,
            self.badges.count >= 8,
            self.story.elite_four_cleared,
            self.story.rayquaza_caught,
            self.story.groudon_caught,
            self.story.kyogre_caught,
            any([self.story.regirock_caught, self.story.regice_caught, self.story.registeel_caught]),
        ]
        return sum(flags) / len(flags)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def summary(self) -> str:
        """Human-readable progress summary."""
        lines = [
            f"=== Pokemon Emerald Progress ===",
            f"Completion: {self.completion_percentage:.1f}%",
            f"Playtime: {self.playtime}",
            f"",
            f"Badges: {self.badges.count}/8",
            f"Pokedex: {self.pokedex.caught} caught / {self.pokedex.seen} seen",
            f"Party: {self.party.count} Pokemon (avg Lv.{self.party.average_level:.0f})",
            f"",
            f"Story Flags:",
        ]
        
        if self.story.has_starter:
            lines.append(f"  ✅ Starter Pokemon")
        if self.story.has_pokedex:
            lines.append(f"  ✅ Pokedex obtained")
        if self.story.elite_four_cleared:
            lines.append(f"  ✅ Elite Four cleared!")
        if self.story.rayquaza_caught:
            lines.append(f"  ✅ Rayquaza caught")
        
        return "\n".join(lines)


class CompletionTracker:
    """
    Reads game memory to track completion progress.
    
    Call update() periodically to refresh the progress snapshot.
    """
    
    def __init__(self, state_detector: "PokemonGen3StateDetector"):
        self.detector = state_detector
        self.client = state_detector.client
        self.progress = GameProgress()
        self._last_update = 0.0
        self._update_interval = 5.0  # seconds between full updates
        self._save_path: Optional[Path] = None
    
    def set_save_path(self, path: Path):
        """Set path for auto-saving progress."""
        self._save_path = path
        path.parent.mkdir(parents=True, exist_ok=True)
    
    def update(self, force: bool = False) -> GameProgress:
        """
        Update progress snapshot from memory.
        
        Args:
            force: Bypass update interval
            
        Returns:
            Updated GameProgress
        """
        now = time.time()
        if not force and (now - self._last_update) < self._update_interval:
            return self.progress
        
        self._last_update = now
        self.progress.timestamp = now
        
        try:
            self._update_badges()
            self._update_story_flags()
            self._update_pokedex()
            self._update_party()
            self._update_position()
            self._update_playtime()
        except Exception as e:
            logger.error(f"Error updating completion tracker: {e}")
        
        # Auto-save if path set
        if self._save_path:
            self._save_progress()
        
        return self.progress
    
    def _update_badges(self):
        """Read badge flags from memory."""
        b = self.progress.badges
        b.stone = self.detector.get_event_flag(Mem.BADGE_1_STONE)
        b.knuckle = self.detector.get_event_flag(Mem.BADGE_2_KNUCKLE)
        b.dynamo = self.detector.get_event_flag(Mem.BADGE_3_DYNAMO)
        b.heat = self.detector.get_event_flag(Mem.BADGE_4_HEAT)
        b.balance = self.detector.get_event_flag(Mem.BADGE_5_BALANCE)
        b.feather = self.detector.get_event_flag(Mem.BADGE_6_FEATHER)
        b.mind = self.detector.get_event_flag(Mem.BADGE_7_MIND)
        b.rain = self.detector.get_event_flag(Mem.BADGE_8_RAIN)
    
    def _update_story_flags(self):
        """Read story progression flags."""
        s = self.progress.story
        s.has_starter = self.detector.get_event_flag(Mem.FLAG_SYS_POKEMON_GET)
        s.has_pokedex = self.detector.get_event_flag(Mem.FLAG_SYS_POKEDEX_GET)
        s.has_pokenav = self.detector.get_event_flag(Mem.FLAG_SYS_POKENAV_GET)
        s.clock_set = self.detector.get_event_flag(Mem.FLAG_SYS_CLOCK_SET)
        s.elite_four_cleared = self.detector.get_event_flag(Mem.FLAG_DEFEATED_ELITE_FOUR)
        
        # Legendaries
        s.rayquaza_caught = self.detector.get_event_flag(Mem.FLAG_HIDE_RAYQUAZA)
        s.groudon_caught = self.detector.get_event_flag(Mem.FLAG_HIDE_GROUDON)
        s.kyogre_caught = self.detector.get_event_flag(Mem.FLAG_HIDE_KYOGRE)
        s.regirock_caught = self.detector.get_event_flag(Mem.FLAG_CAUGHT_REGIROCK)
        s.regice_caught = self.detector.get_event_flag(Mem.FLAG_CAUGHT_REGICE)
        s.registeel_caught = self.detector.get_event_flag(Mem.FLAG_CAUGHT_REGISTEEL)
        s.latias_caught = self.detector.get_event_flag(Mem.FLAG_CAUGHT_LATIAS)
        s.latios_caught = self.detector.get_event_flag(Mem.FLAG_CAUGHT_LATIOS)
    
    def _update_pokedex(self):
        """Count Pokedex seen/caught from flag arrays."""
        try:
            # Read owned flags (52 bytes = 416 bits, we need first 386)
            owned_data = self.client.read_range(
                self.detector._save_block_2 + Mem.POKEDEX_OWNED_OFFSET, 49  # 386/8 = 48.25
            )
            seen_data = self.client.read_range(
                self.detector._save_block_2 + Mem.POKEDEX_SEEN_OFFSET, 49
            )
            
            caught = 0
            seen = 0
            for i in range(386):
                byte_idx = i // 8
                bit_idx = i % 8
                if byte_idx < len(owned_data) and (owned_data[byte_idx] & (1 << bit_idx)):
                    caught += 1
                if byte_idx < len(seen_data) and (seen_data[byte_idx] & (1 << bit_idx)):
                    seen += 1
            
            self.progress.pokedex.caught = caught
            self.progress.pokedex.seen = seen
            
        except Exception as e:
            logger.debug(f"Pokedex read failed: {e}")
    
    def _update_party(self):
        """Read party snapshot."""
        try:
            party = self.detector.read_party()
            snap = self.progress.party
            snap.count = party.count
            snap.total_levels = sum(p.level for p in party.pokemon)
            snap.highest_level = max((p.level for p in party.pokemon), default=0)
            snap.all_healthy = not party.all_fainted and all(
                not p.is_fainted for p in party.pokemon
            )
        except Exception as e:
            logger.debug(f"Party read failed: {e}")
    
    def _update_position(self):
        """Read player map position."""
        try:
            x, y = self.detector.get_player_position()
            group, num = self.detector.get_map_location()
            self.progress.player_x = x
            self.progress.player_y = y
            self.progress.map_group = group
            self.progress.map_num = num
        except Exception as e:
            logger.debug(f"Position read failed: {e}")
    
    def _update_playtime(self):
        """Read play time."""
        try:
            hours, minutes, seconds = self.detector.get_play_time()
            self.progress.playtime.hours = hours
            self.progress.playtime.minutes = minutes
            self.progress.playtime.seconds = seconds
        except Exception as e:
            logger.debug(f"Playtime read failed: {e}")
    
    def _save_progress(self):
        """Save progress to JSON file."""
        if not self._save_path:
            return
        try:
            with open(self._save_path, 'w') as f:
                json.dump(self.progress.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def load_progress(self, path: Path) -> Optional[GameProgress]:
        """Load previously saved progress."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            # TODO: deserialize properly
            return self.progress
        except Exception as e:
            logger.error(f"Failed to load progress: {e}")
            return None
