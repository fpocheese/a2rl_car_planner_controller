from __future__ import annotations

import unittest

import torch

from reference_implementation.tqc import (
    GameGuidedTQC,
    tire_force_utilization,
    truncated_target,
)


class TQCTests(unittest.TestCase):
    def test_tire_force_utilization_and_policy_projection(self) -> None:
        rho = tire_force_utilization(
            normal_acceleration=torch.tensor([0.0, 5.0]),
            tangential_acceleration=torch.tensor([0.0, 4.0]),
            normal_limit=torch.tensor([10.0, 10.0]),
            tangential_limit=torch.tensor([8.0, 8.0]),
        )
        self.assertEqual(float(rho[0]), 0.0)
        self.assertGreater(float(rho[1]), 1.0)

        def fixture_projector(observation: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
            del observation
            projected = action.clone()
            projected[:, 3] = projected[:, 3].clamp(max=0.0)
            return projected

        model = GameGuidedTQC(action_projector=fixture_projector)
        action, _, mean = model.constrained_policy_action(
            torch.randn(6, 51), deterministic=True
        )
        self.assertTrue(torch.all(action[:, 3] <= 0.0))
        self.assertTrue(torch.all(mean[:, 3] <= 0.0))

    def test_target_and_all_training_losses_are_active(self) -> None:
        torch.manual_seed(7)
        batch = 8
        model = GameGuidedTQC()
        observations = torch.randn(batch, 51)
        actions = torch.tanh(torch.randn(batch, 10))
        next_atoms = torch.randn(batch, 2, 25)
        target = truncated_target(
            reward=torch.randn(batch),
            done=torch.zeros(batch),
            next_quantiles=next_atoms,
            next_log_probability=torch.randn(batch, 1),
            entropy_temperature=0.2,
        )
        self.assertEqual(tuple(target.shape), (batch, 46))

        losses = model.losses(
            observation=observations,
            replay_action=actions,
            target_atoms=target,
            game_prior=torch.full((batch, 10), 0.25),
            robust_game_value=torch.full((batch,), 1.5),
            entropy_temperature=0.2,
            prior_weights=torch.tensor([2, 2, 3, 1, 3, 3, 4, 1, 2, 0.5], dtype=torch.float32),
            lambda_actor=1.0,
            lambda_prior=0.2,
            lambda_game=0.1,
        )
        self.assertGreater(float(losses.prior.detach()), 0.0)
        self.assertGreater(float(losses.game.detach()), 0.0)
        losses.total.backward()
        self.assertIsNotNone(model.game_head.network[0].weight.grad)
        self.assertNotIn("game_head", model.inference_state_dict())


if __name__ == "__main__":
    unittest.main()
