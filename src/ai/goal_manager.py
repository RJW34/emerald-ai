"""
Goal Manager for Pokemon Emerald AI.

Determines what the bot should do next based on current game progress.
Provides ordered objectives for progressing toward 100% completion.
"""

import logging
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tracking.completion_tracker import GameProgress

logger = logging.getLogger(__name__)


class GoalType(Enum):
    """Types of goals the bot can pursue."""
    STORY_EVENT = auto()      # Main story progression
    GYM_BADGE = auto()        # Gym challenges
    LEGENDARY = auto()        # Legendary Pokemon encounters
    EXPLORATION = auto()      # Area exploration / item collection
    TRAINING = auto()         # Level grinding
    POKEDEX = auto()         # Pokemon catching


@dataclass
class Goal:
    """
    A specific objective for the bot to pursue.
    
    Attributes:
        goal_type: Category of goal
        description: Human-readable description
        target_map: (map_group, map_num) for navigation
        target_position: (x, y) within the map, if applicable
        prerequisites: What must be true before attempting this goal
        completion_check: How to verify the goal is complete
    """
    goal_type: GoalType
    description: str
    priority: int = 0  # Higher = more urgent
    
    # Navigation targets
    target_map: Optional[tuple[int, int]] = None
    target_position: Optional[tuple[int, int]] = None
    
    # Conditions
    min_party_level: int = 0
    required_badges: int = 0
    
    def __repr__(self) -> str:
        return f"Goal({self.description}, priority={self.priority})"


class GoalManager:
    """
    Determines the next objective based on current progress.
    
    Progression order for Emerald:
    1. Get starter + Pokedex (handled by new game flow)
    2. Petalburg Woods → Rustboro City
    3. Badge 1: Roxanne (Rustboro Gym)
    4. Deliver Devon Goods → Dewford Town
    5. Badge 2: Brawly (Dewford Gym)  
    6. Granite Cave → deliver letter
    7. Badge 3: Wattson (Mauville Gym)
    8. Route 111/112 → Fallarbor → Mt. Chimney
    9. Badge 4: Flannery (Lavaridge Gym)
    10. Badge 5: Norman (Petalburg Gym)
    11. Surf → route to Fortree
    12. Badge 6: Winona (Fortree Gym)
    13. Mt. Pyre → Team Magma/Aqua events
    14. Mossdeep + Space Center events
    15. Badge 7: Tate & Liza (Mossdeep Gym)
    16. Sootopolis crisis → Rayquaza → Wallace awakening
    17. Badge 8: Wallace (Sootopolis Gym)
    18. Victory Road → Elite Four
    19. Post-game: Battle Frontier, legendaries, 100% completion
    """
    
    def __init__(self):
        self._current_goal: Optional[Goal] = None
        
    def determine_next_goal(self, progress: "GameProgress") -> Goal:
        """
        Analyze current progress and return the next objective.
        
        Returns:
            Goal to pursue
        """
        badges = progress.badges.count
        story = progress.story
        
        # Early game: Get starter and Pokedex
        if not story.has_starter:
            return Goal(
                goal_type=GoalType.STORY_EVENT,
                description="Complete new game intro (get starter + Pokedex)",
                priority=100
            )
        
        # Badge progression
        if badges == 0:
            # First badge: Roxanne in Rustboro
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Roxanne for Stone Badge (Rustboro Gym)",
                priority=90,
                target_map=(1, 40),  # Rustboro City (example - verify actual map IDs)
                min_party_level=12
            )
        
        elif badges == 1:
            # Second badge: Brawly in Dewford
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Brawly for Knuckle Badge (Dewford Gym)",
                priority=90,
                target_map=(1, 25),  # Dewford Town (example - verify)
                min_party_level=16,
                required_badges=1
            )
        
        elif badges == 2:
            # Third badge: Wattson in Mauville
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Wattson for Dynamo Badge (Mauville Gym)",
                priority=90,
                target_map=(1, 45),  # Mauville City (example)
                min_party_level=20,
                required_badges=2
            )
        
        elif badges == 3:
            # Fourth badge: Flannery in Lavaridge
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Flannery for Heat Badge (Lavaridge Gym)",
                priority=90,
                target_map=(1, 65),  # Lavaridge Town (example)
                min_party_level=27,
                required_badges=3
            )
        
        elif badges == 4:
            # Fifth badge: Norman in Petalburg (parent gym)
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Norman for Balance Badge (Petalburg Gym)",
                priority=90,
                target_map=(1, 15),  # Petalburg City (example)
                min_party_level=31,
                required_badges=4
            )
        
        elif badges == 5:
            # Sixth badge: Winona in Fortree
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Winona for Feather Badge (Fortree Gym)",
                priority=90,
                target_map=(1, 70),  # Fortree City (example)
                min_party_level=35,
                required_badges=5
            )
        
        elif badges == 6:
            # Seventh badge: Tate & Liza in Mossdeep
            return Goal(
                goal_type=GoalType.GYM_BADGE,
                description="Challenge Tate & Liza for Mind Badge (Mossdeep Gym)",
                priority=90,
                target_map=(1, 75),  # Mossdeep City (example)
                min_party_level=42,
                required_badges=6
            )
        
        elif badges == 7:
            # Eighth badge: Wallace in Sootopolis (requires Rayquaza event first)
            if not story.rayquaza_caught:
                return Goal(
                    goal_type=GoalType.LEGENDARY,
                    description="Complete Rayquaza event at Sky Pillar",
                    priority=95,
                    target_map=(2, 10),  # Sky Pillar (example)
                    min_party_level=45,
                    required_badges=7
                )
            else:
                return Goal(
                    goal_type=GoalType.GYM_BADGE,
                    description="Challenge Wallace for Rain Badge (Sootopolis Gym)",
                    priority=90,
                    target_map=(1, 80),  # Sootopolis City (example)
                    min_party_level=48,
                    required_badges=7
                )
        
        elif badges == 8:
            # Post-badges: Elite Four
            if not story.elite_four_cleared:
                return Goal(
                    goal_type=GoalType.STORY_EVENT,
                    description="Challenge the Elite Four at Ever Grande City",
                    priority=100,
                    target_map=(3, 1),  # Pokemon League (example)
                    min_party_level=55,
                    required_badges=8
                )
            else:
                # Post-game: Battle Frontier or legendary hunting
                if not story.groudon_caught:
                    return Goal(
                        goal_type=GoalType.LEGENDARY,
                        description="Catch Groudon at Terra Cave",
                        priority=70,
                        min_party_level=60,
                        required_badges=8
                    )
                elif not story.kyogre_caught:
                    return Goal(
                        goal_type=GoalType.LEGENDARY,
                        description="Catch Kyogre at Marine Cave",
                        priority=70,
                        min_party_level=60,
                        required_badges=8
                    )
                elif not story.regirock_caught:
                    return Goal(
                        goal_type=GoalType.LEGENDARY,
                        description="Catch Regirock in Desert Ruins",
                        priority=60,
                        min_party_level=60,
                        required_badges=8
                    )
                elif not story.regice_caught:
                    return Goal(
                        goal_type=GoalType.LEGENDARY,
                        description="Catch Regice in Island Cave",
                        priority=60,
                        min_party_level=60,
                        required_badges=8
                    )
                elif not story.registeel_caught:
                    return Goal(
                        goal_type=GoalType.LEGENDARY,
                        description="Catch Registeel in Ancient Tomb",
                        priority=60,
                        min_party_level=60,
                        required_badges=8
                    )
                else:
                    # Default: Pokedex completion or exploration
                    return Goal(
                        goal_type=GoalType.POKEDEX,
                        description=f"Complete Pokedex ({progress.pokedex.caught}/202 caught)",
                        priority=50,
                        min_party_level=60
                    )
        
        # Fallback: explore and train
        return Goal(
            goal_type=GoalType.EXPLORATION,
            description="Explore and train Pokemon",
            priority=10
        )
    
    def check_prerequisites(self, goal: Goal, progress: "GameProgress") -> tuple[bool, str]:
        """
        Check if prerequisites for a goal are met.
        
        Returns:
            (can_attempt, reason_if_not)
        """
        # Check badge requirement
        if progress.badges.count < goal.required_badges:
            return False, f"Need {goal.required_badges} badges (have {progress.badges.count})"
        
        # Check party level requirement
        if goal.min_party_level > 0:
            if progress.party.highest_level < goal.min_party_level:
                return False, f"Party too weak (need Lv.{goal.min_party_level}, highest is Lv.{progress.party.highest_level})"
        
        # Check party health
        if not progress.party.all_healthy:
            return False, "Party needs healing at Pokemon Center"
        
        return True, ""
    
    def suggest_training_goal(self, current_level: int, target_level: int) -> Goal:
        """Create a training goal to reach target level."""
        return Goal(
            goal_type=GoalType.TRAINING,
            description=f"Train party to Lv.{target_level} (current highest: Lv.{current_level})",
            priority=80,
            min_party_level=target_level
        )
