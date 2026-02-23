"""
State detection for Pokemon Emerald.

States:
  TITLE    — title screen / intro, save block pointer = 0
  INTRO    — between title and first overworld frame (pointer valid, battle = 0, but
              game is still in intro sequence / naming / Oak speech)
  OVERWORLD — in the world, not in battle
  BATTLE   — battle type flags non-zero
"""

from enum import Enum, auto
from .memory_map import (
    SAVE_BLOCK_1_PTR,
    BATTLE_TYPE_FLAGS,
    VALID_SAVE_PTR_MIN,
    VALID_SAVE_PTR_MAX,
)


class State(Enum):
    TITLE = auto()
    INTRO = auto()
    OVERWORLD = auto()
    BATTLE = auto()


# How long (in detection calls) the pointer must be valid before we trust OVERWORLD.
# Prevents false positives during intro frames where the pointer briefly becomes valid.
_STABLE_FRAMES = 10


class StateDetector:
    def __init__(self, client):
        self._c = client
        self._stable = 0  # consecutive frames with valid ptr + no battle
        self._prev = State.TITLE

    def detect(self) -> State:
        sb1 = self._c.r32(SAVE_BLOCK_1_PTR)
        ptr_valid = VALID_SAVE_PTR_MIN <= sb1 < VALID_SAVE_PTR_MAX

        if not ptr_valid:
            self._stable = 0
            return State.TITLE

        battle = self._c.r32(BATTLE_TYPE_FLAGS)
        if battle != 0:
            self._stable = 0
            return State.BATTLE

        self._stable += 1
        if self._stable >= _STABLE_FRAMES:
            return State.OVERWORLD

        return State.INTRO
