"""Hysteretic tactical finite-state machine with passing-side lock."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .action import TacticalAction


class Mode(str, Enum):
    RACELINE = "raceline"
    SHADOW = "shadow"
    OVERTAKE = "overtake"
    HOLD = "hold"
    DEFEND = "defend"


@dataclass(frozen=True)
class FSMConfig:
    min_overtake_width: float
    min_relative_speed: float
    defend_front_gap: float
    defend_rear_gap: float
    safe_lateral_separation: float
    interlock_gap: float


@dataclass(frozen=True)
class FSMObservation:
    gap: float
    rear_gap: float
    left_space: float
    right_space: float
    ego_minus_opponent_speed: float
    min_predicted_lateral_separation: float
    delta_s: float
    immunity_expired: bool = True
    outside_line_tight_bend: bool = False
    duel_terminated: bool = False


@dataclass(frozen=True)
class FSMTransition:
    mode: Mode
    locked_side: int
    ready: bool
    aborted: bool


class TacticalFSM:
    def __init__(self, config: FSMConfig, mode: Mode = Mode.RACELINE, locked_side: int = 0) -> None:
        self.config = config
        self.mode = mode
        self.locked_side = int(locked_side)

    def _ready(self, observation: FSMObservation, side: int) -> bool:
        side_space = observation.left_space if side > 0 else observation.right_space
        return (
            side_space >= self.config.min_overtake_width
            and observation.ego_minus_opponent_speed >= self.config.min_relative_speed
            and not observation.outside_line_tight_bend
        )

    def step(self, observation: FSMObservation, action: TacticalAction) -> FSMTransition:
        if observation.duel_terminated:
            self.locked_side = 0

        requested_side = action.side
        active_side = self.locked_side if self.locked_side else requested_side
        ready = self._ready(observation, active_side)
        aborted = (
            observation.gap > action.abort_gap
            or (
                observation.min_predicted_lateral_separation
                < self.config.safe_lateral_separation
                and abs(observation.delta_s) < self.config.interlock_gap
            )
        )

        # Ordering follows the piecewise definition in Eq. (FSM).
        if observation.gap <= action.overtake_gap and ready and observation.immunity_expired:
            new_mode = Mode.OVERTAKE
        elif action.overtake_gap < observation.gap <= action.chase_gap:
            new_mode = Mode.SHADOW
        elif self.mode is Mode.OVERTAKE and aborted:
            new_mode = Mode.HOLD
        elif (
            observation.gap > self.config.defend_front_gap
            and 0.0 < observation.rear_gap < self.config.defend_rear_gap
            and observation.immunity_expired
        ):
            new_mode = Mode.DEFEND
        elif observation.gap > action.chase_gap:
            new_mode = Mode.RACELINE
        else:
            new_mode = self.mode

        if new_mode is Mode.OVERTAKE and self.locked_side == 0:
            self.locked_side = requested_side
        self.mode = new_mode
        return FSMTransition(new_mode, self.locked_side, ready, aborted)
