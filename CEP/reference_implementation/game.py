"""Stackelberg leader--follower target generation with IBR.

The solver is deliberately callback based: vehicle dynamics and utilities are
experiment-specific, whereas the IBR, local response set, robust minimization,
safe leader selection, and actor-prior conversion are structural parts of the
reported method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from .action import physical_to_normalized, project_physical

FollowerBestResponse = Callable[[int, np.ndarray, np.ndarray, Any], np.ndarray]
LeaderUtility = Callable[[np.ndarray, np.ndarray, Any], float]
SafeAction = Callable[[np.ndarray, Any], bool]


@dataclass(frozen=True)
class GameTarget:
    physical_action: np.ndarray
    normalized_action: np.ndarray
    follower_response: np.ndarray
    robust_value: float
    iterations: int
    converged: bool


class StackelbergIBR:
    """Finite-candidate Stackelberg solver with continuous follower IBR."""

    def __init__(
        self,
        follower_best_response: FollowerBestResponse,
        leader_utility: LeaderUtility,
        response_radius: float,
        max_iterations: int,
        tolerance: float,
        safe_action: SafeAction | None = None,
        follower_low: Sequence[float] | None = None,
        follower_high: Sequence[float] | None = None,
    ) -> None:
        if response_radius < 0:
            raise ValueError("response_radius must be non-negative")
        self.follower_best_response = follower_best_response
        self.leader_utility = leader_utility
        self.safe_action = safe_action or (lambda action, context: True)
        self.response_radius = float(response_radius)
        self.max_iterations = int(max_iterations)
        self.tolerance = float(tolerance)
        self.follower_low = None if follower_low is None else np.asarray(follower_low, dtype=float)
        self.follower_high = None if follower_high is None else np.asarray(follower_high, dtype=float)

    def solve_followers(
        self,
        leader_action: Sequence[float],
        initial_response: Sequence[Sequence[float]],
        context: Any = None,
    ) -> tuple[np.ndarray, int, bool]:
        leader = np.asarray(leader_action, dtype=float)
        response = np.asarray(initial_response, dtype=float).copy()
        if response.ndim != 2:
            raise ValueError("initial_response must have shape [followers, variables]")

        for iteration in range(1, self.max_iterations + 1):
            previous = response.copy()
            for follower_index in range(response.shape[0]):
                update = np.asarray(
                    self.follower_best_response(follower_index, leader, response.copy(), context),
                    dtype=float,
                )
                if update.shape != response[follower_index].shape:
                    raise ValueError("follower best response returned an incompatible shape")
                if self.follower_low is not None:
                    update = np.maximum(update, self.follower_low)
                if self.follower_high is not None:
                    update = np.minimum(update, self.follower_high)
                response[follower_index] = update
            if np.linalg.norm(response - previous) <= self.tolerance:
                return response, iteration, True
        return response, self.max_iterations, False

    def response_neighborhood(self, center: np.ndarray) -> Iterable[np.ndarray]:
        """Yield an auditable axis stencil inside the local response ball."""

        yield center.copy()
        flat = center.reshape(-1)
        for coordinate in range(flat.size):
            for sign in (-1.0, 1.0):
                candidate = flat.copy()
                candidate[coordinate] += sign * self.response_radius
                candidate = candidate.reshape(center.shape)
                if self.follower_low is not None:
                    candidate = np.maximum(candidate, self.follower_low)
                if self.follower_high is not None:
                    candidate = np.minimum(candidate, self.follower_high)
                yield candidate

    def robust_value(self, leader_action: np.ndarray, response: np.ndarray, context: Any) -> float:
        return min(
            float(self.leader_utility(leader_action, candidate, context))
            for candidate in self.response_neighborhood(response)
        )

    def solve(
        self,
        leader_candidates: Sequence[Sequence[float]],
        initial_response: Sequence[Sequence[float]],
        context: Any = None,
    ) -> GameTarget:
        """Return the safe action with maximum local robust tactical value."""

        best: GameTarget | None = None
        for raw_candidate in leader_candidates:
            action = project_physical(raw_candidate)
            if not self.safe_action(action, context):
                continue
            response, iterations, converged = self.solve_followers(action, initial_response, context)
            value = self.robust_value(action, response, context)
            target = GameTarget(
                physical_action=action,
                normalized_action=physical_to_normalized(action),
                follower_response=response,
                robust_value=value,
                iterations=iterations,
                converged=converged,
            )
            if best is None or target.robust_value > best.robust_value:
                best = target
        if best is None:
            raise RuntimeError("no leader candidate passed the safe-action filter")
        return best
