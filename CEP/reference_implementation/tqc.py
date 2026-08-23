"""Game-guided Truncated Quantile Critics modules and losses.

The auxiliary game-value head and IBR prior loss are training-time modules.
They need not be present in a deployment-only actor archive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import torch
from torch import Tensor, nn
from torch.distributions import Normal


ActionProjector = Callable[[Tensor, Tensor], Tensor]


def tire_force_utilization(
    normal_acceleration: Tensor,
    tangential_acceleration: Tensor,
    normal_limit: Tensor,
    tangential_limit: Tensor,
    exponent: float = 0.75,
) -> Tensor:
    """Return the dimensionless tire-force-envelope utilization rho.

    The caller obtains the speed-dependent limits from the tire model and may
    evaluate this function over every preview station.  Values not exceeding
    one satisfy the super-elliptic feasibility constraint in the manuscript.
    """

    if exponent <= 0.0:
        raise ValueError("exponent must be positive")
    if torch.any(normal_limit <= 0.0) or torch.any(tangential_limit <= 0.0):
        raise ValueError("tire-force limits must be positive")
    return (
        (normal_acceleration.abs() / normal_limit).pow(exponent)
        + (tangential_acceleration.abs() / tangential_limit).pow(exponent)
    )


def _mlp(input_dim: int, hidden: Sequence[int], output_dim: int) -> nn.Sequential:
    layers: list[nn.Module] = []
    previous = input_dim
    for width in hidden:
        layers.extend((nn.Linear(previous, width), nn.ReLU()))
        previous = width
    layers.append(nn.Linear(previous, output_dim))
    return nn.Sequential(*layers)


class SquashedGaussianActor(nn.Module):
    def __init__(self, observation_dim: int = 51, action_dim: int = 10) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(observation_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
        )
        self.mean = nn.Linear(256, action_dim)
        self.log_std = nn.Linear(256, action_dim)

    def distribution_parameters(self, observation: Tensor) -> tuple[Tensor, Tensor]:
        features = self.backbone(observation)
        return self.mean(features), self.log_std(features).clamp(-20.0, 2.0)

    def forward(self, observation: Tensor, deterministic: bool = False) -> tuple[Tensor, Tensor, Tensor]:
        mean, log_std = self.distribution_parameters(observation)
        distribution = Normal(mean, log_std.exp())
        raw = mean if deterministic else distribution.rsample()
        action = torch.tanh(raw)
        log_probability = distribution.log_prob(raw) - torch.log(1.0 - action.square() + 1e-6)
        return action, log_probability.sum(dim=-1, keepdim=True), torch.tanh(mean)


class QuantileCritics(nn.Module):
    def __init__(self, observation_dim: int = 51, action_dim: int = 10, critics: int = 2, atoms: int = 25) -> None:
        super().__init__()
        self.critics = critics
        self.atoms = atoms
        self.networks = nn.ModuleList(
            [_mlp(observation_dim + action_dim, (256, 256), atoms) for _ in range(critics)]
        )

    def forward(self, observation: Tensor, action: Tensor) -> Tensor:
        features = torch.cat((observation, action), dim=-1)
        return torch.stack([network(features) for network in self.networks], dim=1)


class GameValueHead(nn.Module):
    def __init__(self, observation_dim: int = 51, action_dim: int = 10) -> None:
        super().__init__()
        self.network = _mlp(observation_dim + action_dim, (256, 256), 1)

    def forward(self, observation: Tensor, action: Tensor) -> Tensor:
        return self.network(torch.cat((observation, action), dim=-1)).squeeze(-1)


def truncated_target(
    reward: Tensor,
    done: Tensor,
    next_quantiles: Tensor,
    next_log_probability: Tensor,
    entropy_temperature: float,
    gamma: float = 0.99,
    drop_per_critic: int = 2,
) -> Tensor:
    """Construct the sorted, lower-tail TQC target (46 atoms by default)."""

    if next_quantiles.ndim != 3:
        raise ValueError("next_quantiles must have shape [batch, critics, atoms]")
    batch = next_quantiles.shape[0]
    entropy_adjusted = next_quantiles - entropy_temperature * next_log_probability.reshape(batch, 1, 1)
    flattened = entropy_adjusted.reshape(batch, -1).sort(dim=1).values
    retain = flattened.shape[1] - drop_per_critic * next_quantiles.shape[1]
    if retain <= 0:
        raise ValueError("drop_per_critic removes all target atoms")
    return reward.reshape(batch, 1) + gamma * (1.0 - done.reshape(batch, 1)) * flattened[:, :retain]


def quantile_huber_loss(predicted: Tensor, target: Tensor, kappa: float = 1.0) -> Tensor:
    """Quantile-Huber regression for [B,C,N] predictions and [B,K] targets."""

    if predicted.ndim != 3 or target.ndim != 2:
        raise ValueError("expected predicted [B,C,N] and target [B,K]")
    delta = target[:, None, None, :] - predicted[:, :, :, None]
    absolute = delta.abs()
    huber = torch.where(absolute <= kappa, 0.5 * delta.square(), kappa * (absolute - 0.5 * kappa))
    atoms = predicted.shape[-1]
    tau = (torch.arange(atoms, device=predicted.device, dtype=predicted.dtype) + 0.5) / atoms
    weight = (tau[None, None, :, None] - (delta.detach() < 0).to(predicted.dtype)).abs()
    return (weight * huber / kappa).mean()


@dataclass(frozen=True)
class LossBundle:
    total: Tensor
    critic: Tensor
    actor: Tensor
    prior: Tensor
    game: Tensor


class GameGuidedTQC(nn.Module):
    def __init__(
        self,
        observation_dim: int = 51,
        action_dim: int = 10,
        action_projector: ActionProjector | None = None,
    ) -> None:
        super().__init__()
        self.actor = SquashedGaussianActor(observation_dim, action_dim)
        self.critics = QuantileCritics(observation_dim, action_dim)
        self.game_head = GameValueHead(observation_dim, action_dim)
        self.action_projector = action_projector

    def constrained_policy_action(
        self,
        observation: Tensor,
        deterministic: bool = False,
    ) -> tuple[Tensor, Tensor, Tensor]:
        """Sample the actor and project action/mean onto tire-feasible support.

        During target construction the returned action is passed to the target
        critics.  During actor optimization the same method prevents critic
        evaluation outside the state-dependent tire-force feasible set.  The
        callback closes over the tire-force map and preview quantities needed
        to implement the manuscript's projection.
        """

        action, log_probability, mean = self.actor(observation, deterministic)
        if self.action_projector is None:
            return action, log_probability, mean
        projected_action = self.action_projector(observation, action)
        projected_mean = self.action_projector(observation, mean)
        if projected_action.shape != action.shape or projected_mean.shape != mean.shape:
            raise ValueError("action_projector must preserve the action shape")
        return projected_action, log_probability, projected_mean

    def losses(
        self,
        observation: Tensor,
        replay_action: Tensor,
        target_atoms: Tensor,
        game_prior: Tensor,
        robust_game_value: Tensor,
        entropy_temperature: float,
        lambda_actor: float,
        lambda_prior: float,
        lambda_game: float,
        prior_weights: Tensor | None = None,
    ) -> LossBundle:
        predicted_atoms = self.critics(observation, replay_action)
        critic_loss = quantile_huber_loss(predicted_atoms, target_atoms)

        sampled_action, log_probability, policy_mean = self.constrained_policy_action(observation)
        current_atoms = self.critics(observation, sampled_action)
        actor_loss = (entropy_temperature * log_probability.squeeze(-1) - current_atoms.mean((1, 2))).mean()

        if prior_weights is None:
            prior_weights = torch.ones(game_prior.shape[-1], device=game_prior.device)
        prior_loss = ((policy_mean - game_prior).square() * prior_weights).mean()
        predicted_game_value = self.game_head(observation, replay_action)
        game_loss = (predicted_game_value - robust_game_value).square().mean()
        total = critic_loss + lambda_actor * actor_loss + lambda_prior * prior_loss + lambda_game * game_loss
        return LossBundle(total, critic_loss, actor_loss, prior_loss, game_loss)

    def inference_state_dict(self) -> dict[str, dict[str, Tensor]]:
        """Return the deployment-time actor/critic state without training-only head."""

        return {"actor": self.actor.state_dict(), "critics": self.critics.state_dict()}
