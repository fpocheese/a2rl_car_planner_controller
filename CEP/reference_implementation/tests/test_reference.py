from __future__ import annotations

import unittest

import numpy as np

from reference_implementation.action import map_and_project, project_physical
from reference_implementation.corridor import CorridorCarver, CorridorConfig, OpponentFootprint
from reference_implementation.fsm import FSMConfig, FSMObservation, Mode, TacticalFSM
from reference_implementation.game import StackelbergIBR


class ActionTests(unittest.TestCase):
    def test_projection_enforces_reported_relations(self) -> None:
        candidate = np.asarray([1.5, 1.5, 0.5, 70.0, 18.0, 24.0, 20.0, 0.0, 2.0, 0.2])
        action = project_physical(candidate)
        self.assertGreaterEqual(action[4], action[5] - 2.0)
        self.assertGreaterEqual(action[5], action[4] - 6.0)
        self.assertGreaterEqual(action[6], action[4] + 5.0)


class GameTests(unittest.TestCase):
    def test_ibr_generates_nonzero_prior_and_value(self) -> None:
        def follower_best_response(index, leader, responses, context):
            return 0.5 * leader[:2]

        def leader_utility(leader, responses, context):
            target = context["target"]
            return -float(np.square(leader - target).sum()) - 0.1 * float(np.square(responses).sum())

        centre = map_and_project(np.zeros(10)).as_array()
        candidates = [centre, centre + np.asarray([0, 0, 0, 0, 0, 0, 0, 0.5, 0, 0])]
        solver = StackelbergIBR(
            follower_best_response,
            leader_utility,
            response_radius=0.02,
            max_iterations=30,
            tolerance=1e-5,
        )
        result = solver.solve(candidates, np.zeros((1, 2)), {"target": centre})
        self.assertTrue(result.converged)
        self.assertEqual(result.normalized_action.shape, (10,))
        self.assertNotEqual(result.robust_value, 0.0)


class FSMAndCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.action = map_and_project(np.zeros(10))
        self.fsm = TacticalFSM(
            FSMConfig(
                min_overtake_width=3.0,
                min_relative_speed=1.0,
                defend_front_gap=25.0,
                defend_rear_gap=15.0,
                safe_lateral_separation=1.0,
                interlock_gap=10.0,
            )
        )

    def test_side_is_locked_on_overtake(self) -> None:
        observation = FSMObservation(
            gap=15.0,
            rear_gap=30.0,
            left_space=4.0,
            right_space=4.0,
            ego_minus_opponent_speed=2.0,
            min_predicted_lateral_separation=2.0,
            delta_s=5.0,
        )
        transition = self.fsm.step(observation, self.action)
        self.assertEqual(transition.mode, Mode.OVERTAKE)
        self.assertEqual(transition.locked_side, 1)

    def test_corridor_excludes_opponent_and_preserves_minimum_width(self) -> None:
        config = CorridorConfig(
            fade_distance=40.0,
            fade_power=2.0,
            blend_stations=5,
            shadow_exclusion_scale=0.5,
            defend_exclusion_scale=0.5,
            stations=20,
            minimum_width=3.0,
        )
        carver = CorridorCarver(config)
        opponent = OpponentFootprint(10.0, 0.0, 0.0, 5.0, 2.0)
        corridor = carver.carve(
            ego_progress=0.0,
            track_lower=np.full(20, -6.0),
            track_upper=np.full(20, 6.0),
            opponent=opponent,
            action=self.action,
            mode=Mode.OVERTAKE,
            locked_side=1,
        )
        self.assertTrue(np.all(corridor.upper - corridor.lower >= 3.0 - 1e-12))
        self.assertGreater(corridor.lower[5], 0.0)


if __name__ == "__main__":
    unittest.main()
