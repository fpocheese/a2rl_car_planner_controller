"""Deterministic Frenet tactical-corridor carver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .action import TacticalAction
from .fsm import Mode


@dataclass(frozen=True)
class CorridorConfig:
    fade_distance: float
    fade_power: float
    blend_stations: int
    shadow_exclusion_scale: float
    defend_exclusion_scale: float
    station_spacing: float = 2.0
    stations: int = 150
    minimum_width: float = 3.0
    ema_beta: float = 0.2

    def __post_init__(self) -> None:
        if self.fade_distance <= 0.0 or self.fade_power <= 0.0:
            raise ValueError("fade distance and power must be positive")
        if self.blend_stations <= 0 or self.stations <= 0 or self.station_spacing <= 0.0:
            raise ValueError("station and blending parameters must be positive")
        if self.shadow_exclusion_scale < 0.0 or self.defend_exclusion_scale < 0.0:
            raise ValueError("mode exclusion scales must be non-negative")
        if not 0.0 <= self.ema_beta <= 1.0:
            raise ValueError("ema_beta must lie in [0, 1]")


@dataclass(frozen=True)
class OpponentFootprint:
    progress: float
    lateral: float
    heading_error: float
    length: float
    width: float

    @property
    def lateral_half_extent(self) -> float:
        return 0.5 * (
            self.length * abs(np.sin(self.heading_error))
            + self.width * abs(np.cos(self.heading_error))
        )

    @property
    def longitudinal_half_extent(self) -> float:
        return 0.5 * (
            self.length * abs(np.cos(self.heading_error))
            + self.width * abs(np.sin(self.heading_error))
        )


@dataclass(frozen=True)
class Corridor:
    station_progress: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


class CorridorCarver:
    def __init__(self, config: CorridorConfig) -> None:
        self.config = config

    def _fade(self, delta_progress: np.ndarray) -> np.ndarray:
        ratio = np.abs(delta_progress) / self.config.fade_distance
        inside = ratio < 1.0
        fade = np.zeros_like(ratio)
        fade[inside] = np.cos(0.5 * np.pi * ratio[inside]) ** self.config.fade_power
        return fade

    def carve(
        self,
        ego_progress: float,
        track_lower: Sequence[float],
        track_upper: Sequence[float],
        opponent: OpponentFootprint | None,
        action: TacticalAction,
        mode: Mode,
        locked_side: int,
        previous: Corridor | None = None,
    ) -> Corridor:
        lower_track = np.asarray(track_lower, dtype=float)
        upper_track = np.asarray(track_upper, dtype=float)
        expected = (self.config.stations,)
        if lower_track.shape != expected or upper_track.shape != expected:
            raise ValueError(f"track bounds must each have shape {expected}")
        if np.any(upper_track <= lower_track):
            raise ValueError("physical track upper bounds must exceed lower bounds")

        station_progress = ego_progress + self.config.station_spacing * np.arange(self.config.stations)
        lower = lower_track.copy()
        upper = upper_track.copy()
        side = locked_side if locked_side else action.side

        if opponent is not None and mode in {Mode.SHADOW, Mode.OVERTAKE, Mode.DEFEND}:
            delta = station_progress - opponent.progress
            fade = self._fade(delta)
            exclusion = opponent.lateral_half_extent + 0.5 * opponent.width + action.safe_clearance

            # OVERTAKE implements Eq. (overtake bound). SHADOW applies a
            # configured side-consistent scale to form a preparation funnel.
            # DEFEND uses its separately configured scale and mirrors the side
            # to occupy the opponent's forward line.
            if mode is Mode.OVERTAKE:
                strength = 1.0
            elif mode is Mode.SHADOW:
                strength = self.config.shadow_exclusion_scale
            else:
                strength = self.config.defend_exclusion_scale
            effective_side = -side if mode is Mode.DEFEND else side
            if effective_side > 0:
                lower = np.maximum(lower, opponent.lateral + strength * exclusion * fade)
            else:
                upper = np.minimum(upper, opponent.lateral - strength * exclusion * fade)

        # Raceline and Hold retain the full physical width as stated in the
        # mode semantics.  Active interaction modes receive the learned caps.
        if mode in {Mode.SHADOW, Mode.OVERTAKE, Mode.DEFEND}:
            index = np.arange(self.config.stations, dtype=float)
            blend = np.minimum(1.0, (index / max(1, self.config.blend_stations)) ** 2)
            capped_upper = np.minimum(upper, action.lateral_bias + action.left_cap)
            capped_lower = np.maximum(lower, action.lateral_bias - action.right_cap)
            upper = (1.0 - blend) * upper + blend * capped_upper
            lower = (1.0 - blend) * lower + blend * capped_lower

        width_tolerance = 1e-9
        invalid = upper - lower < self.config.minimum_width - width_tolerance
        if np.any(invalid):
            if previous is not None:
                previous_valid = (
                    previous.upper - previous.lower >= self.config.minimum_width
                ) & (previous.lower >= lower_track) & (previous.upper <= upper_track)
                hold = invalid & previous_valid
                lower[hold] = previous.lower[hold]
                upper[hold] = previous.upper[hold]
                invalid = upper - lower < self.config.minimum_width - width_tolerance

            # Recover about the current interval centre within physical bounds.
            centre = 0.5 * (lower + upper)
            recovered_lower = np.maximum(lower_track, centre - 0.5 * self.config.minimum_width)
            recovered_upper = np.minimum(upper_track, centre + 0.5 * self.config.minimum_width)
            recovered_valid = recovered_upper - recovered_lower >= self.config.minimum_width - width_tolerance
            use = invalid & recovered_valid
            lower[use] = recovered_lower[use]
            upper[use] = recovered_upper[use]
            if np.any(upper - lower < self.config.minimum_width - width_tolerance):
                raise RuntimeError("minimum corridor width cannot be recovered inside track bounds")

        if previous is not None:
            beta = self.config.ema_beta
            lower = beta * lower + (1.0 - beta) * previous.lower
            upper = beta * upper + (1.0 - beta) * previous.upper
            lower = np.maximum(lower, lower_track)
            upper = np.minimum(upper, upper_track)

        return Corridor(station_progress=station_progress, lower=lower, upper=upper)
