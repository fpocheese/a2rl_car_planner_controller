"""Manuscript-aligned reference implementation of the tactical layer.

The package reconstructs the equations reported in ``a2rl_paper.tex``.  It is
intended for review, reimplementation, and regression testing.  It is not
claimed to be a byte-identical copy of the source revision used for the
reported HIL campaign.
"""

from .action import ACTION_NAMES, ACTION_BOUNDS, TacticalAction, map_and_project
from .corridor import CorridorCarver, CorridorConfig, OpponentFootprint
from .fsm import FSMConfig, FSMObservation, Mode, TacticalFSM
from .game import GameTarget, StackelbergIBR

__all__ = [
    "ACTION_NAMES",
    "ACTION_BOUNDS",
    "TacticalAction",
    "map_and_project",
    "CorridorCarver",
    "CorridorConfig",
    "OpponentFootprint",
    "FSMConfig",
    "FSMObservation",
    "Mode",
    "TacticalFSM",
    "GameTarget",
    "StackelbergIBR",
]
