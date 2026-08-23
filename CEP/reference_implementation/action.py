"""Ten-dimensional tactical action map and safety projection.

Implements Eqs. (action mapping)--(side sign) in the manuscript.  Distances
are metres and speed is m/s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


ACTION_NAMES = (
    "left_cap",
    "right_cap",
    "safe_clearance",
    "speed_cap",
    "chase_gap",
    "overtake_gap",
    "abort_gap",
    "lateral_bias",
    "recovery_width",
    "side_score",
)

ACTION_BOUNDS: Mapping[str, tuple[float, float]] = {
    "left_cap": (1.5, 6.0),
    "right_cap": (1.5, 6.0),
    "safe_clearance": (0.2, 0.8),
    "speed_cap": (15.0, 90.0),
    "chase_gap": (18.0, 24.0),
    "overtake_gap": (16.0, 24.0),
    "abort_gap": (28.0, 45.0),
    "lateral_bias": (-1.5, 1.5),
    "recovery_width": (1.0, 5.0),
    "side_score": (-1.0, 1.0),
}

LOW = np.asarray([ACTION_BOUNDS[name][0] for name in ACTION_NAMES], dtype=float)
HIGH = np.asarray([ACTION_BOUNDS[name][1] for name in ACTION_NAMES], dtype=float)


@dataclass(frozen=True)
class TacticalAction:
    left_cap: float
    right_cap: float
    safe_clearance: float
    speed_cap: float
    chase_gap: float
    overtake_gap: float
    abort_gap: float
    lateral_bias: float
    recovery_width: float
    side_score: float

    @classmethod
    def from_array(cls, values: Sequence[float]) -> "TacticalAction":
        array = np.asarray(values, dtype=float)
        if array.shape != (10,):
            raise ValueError(f"expected a 10-vector, got shape {array.shape}")
        return cls(*array.tolist())

    def as_array(self) -> np.ndarray:
        return np.asarray(tuple(self.__dict__.values()), dtype=float)

    @property
    def side(self) -> int:
        """+1 selects a left-side pass; -1 selects a right-side pass."""

        return 1 if self.side_score >= 0.0 else -1


def normalized_to_physical(normalized: Sequence[float]) -> np.ndarray:
    """Map a tanh-space action in [-1, 1]^10 to physical units."""

    u = np.asarray(normalized, dtype=float)
    if u.shape != (10,):
        raise ValueError(f"expected a 10-vector, got shape {u.shape}")
    u = np.clip(u, -1.0, 1.0)
    return LOW + 0.5 * (u + 1.0) * (HIGH - LOW)


def physical_to_normalized(physical: Sequence[float]) -> np.ndarray:
    """Map a physical action to the actor's normalized coordinate system."""

    a = np.asarray(physical, dtype=float)
    if a.shape != (10,):
        raise ValueError(f"expected a 10-vector, got shape {a.shape}")
    return np.clip(2.0 * (a - LOW) / (HIGH - LOW) - 1.0, -1.0, 1.0)


def project_physical(physical: Sequence[float]) -> np.ndarray:
    """Project an action onto the bounded safety set in Eq. (safety clip).

    The projection is deterministic.  It first clips component bounds, then
    clips the overtake threshold to the admissible interval relative to the
    chase threshold, enforces the abort margin, and finally applies the stated
    numerical width guard.
    """

    a = np.clip(np.asarray(physical, dtype=float), LOW, HIGH)
    if a.shape != (10,):
        raise ValueError(f"expected a 10-vector, got shape {a.shape}")

    chase = a[4]
    a[5] = np.clip(a[5], max(LOW[5], chase - 6.0), min(HIGH[5], chase + 2.0))
    a[6] = max(a[6], chase + 5.0)

    # This is inactive under the reported [1.5, 6] component bounds, but is
    # retained so the implementation mirrors the manuscript's full safe set.
    if a[0] + a[1] < 0.8:
        deficit = 0.8 - (a[0] + a[1])
        a[0] = min(HIGH[0], a[0] + 0.5 * deficit)
        a[1] = min(HIGH[1], a[1] + 0.5 * deficit)
    return a


def map_and_project(normalized: Sequence[float]) -> TacticalAction:
    """Apply the tanh-space affine map followed by the safe projection."""

    return TacticalAction.from_array(project_physical(normalized_to_physical(normalized)))
