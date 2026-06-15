"""Incremental dense reward calculator for A2RL RL.

Keeps state across step()s for sign-flip overtake detection,
progress accumulation, and lap-PB tracking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class RewardWeights:
    # 用户硬性需求 (2026-04-30): 只训练 1v1 主动超车, **不奖励"跑得更远"** → progress=0
    progress: float = 0.0          # 关闭: 不让 ego 单纯通过跑直道刷分
    overtake: float = 30.0         # 加大: 鼓励主动超车
    overtaken_by: float = -20.0    # 加大: 严罚被反超
    collision: float = -100.0      # terminal
    lat_err_quad: float = -2.0     # per step, * |lat_err|^2
    corridor_crushed: float = -5.0 # per step if L+R < 0.8
    approach: float = 3.0          # 加大: 主动贴车 (gap<25 且 closing)
    too_close: float = -3.0        # per step if gap<2 sustained
    lap_pb: float = 5.0            # one-shot when new PB
    smooth: float = -0.1           # per step, * |a-a_prev|^2 (整体 9 维)
    # 2026-04-30 v4: 路径几何相关维度 (corridor L/R + lateral_bias) 额外平滑罚
    # 直接抑制可行域抖动导致的路径前后跳变 (避免猛打方向盘)
    geom_smooth: float = -0.5      # per step, * (dL^2 + dR^2 + d_bias^2)
    safety_clip: float = -0.1      # per step if hard clip activated
    side_by_side: float = 0.5      # per step, 与对手 |del_s|<8 且 |del_n|>1.0 (并排博弈)
    # v23 (2026-04-30 用户反馈"超车可行域太窄"): 在有对手且近距 (gap<30) 时
    # 奖励 RL 选大 corridor L/R margin, 引导策略去争完整赛道可行域.
    # bonus = wide_corridor * (action[0] + action[1]) / 2.0  限在 [1.5, 6.0] 区间 → max +1.5/step
    wide_corridor: float = 0.25


@dataclass
class RewardState:
    last_ego_s: Optional[float] = None
    lap_length: float = 3000.0
    pb_lap: Optional[float] = None
    last_lap_count: int = 0
    last_opp_del_x: Dict[int, float] = field(default_factory=dict)
    last_opp_gap: Dict[int, float] = field(default_factory=dict)
    too_close_steps: int = 0
    last_action: Optional[List[float]] = None
    cumulative_off_steps: int = 0
    cumulative_collisions: int = 0
    n_overtakes: int = 0
    n_overtaken_by: int = 0


def compute_step_reward(
    ego_s: float,
    lat_err: float,
    opps: List[Dict],          # [{id, del_x, del_y, V, ...}, ...]
    corridor_l: float,
    corridor_r: float,
    new_collision: bool,
    new_lap_time: Optional[float],
    action: List[float],
    safety_clipped: bool,
    state: RewardState,
    weights: RewardWeights = RewardWeights(),
) -> Tuple[float, Dict[str, float]]:
    """Compute reward increment for this step. Mutates `state` in place."""
    parts: Dict[str, float] = {}

    # ---- Progress (handles wrap-around) ----
    if state.last_ego_s is not None:
        ds = ego_s - state.last_ego_s
        if ds < -state.lap_length / 2:
            ds += state.lap_length
        elif ds > state.lap_length / 2:
            ds -= state.lap_length
        # Cap absurd jumps
        ds = max(-1.0, min(ds, 5.0))
        parts['progress'] = weights.progress * ds
    state.last_ego_s = ego_s

    # ---- Overtake / overtaken_by (sign-flip on del_x with hysteresis) ----
    parts['overtake'] = 0.0
    parts['overtaken_by'] = 0.0
    for opp in opps:
        oid = opp['id']
        dx = opp['del_x']
        prev = state.last_opp_del_x.get(oid)
        if prev is not None and abs(dx) > 4.0 and abs(prev) > 4.0:
            # transition from in-front (+) to behind (-) = overtake
            if prev > 0 and dx < 0:
                parts['overtake'] += weights.overtake
                state.n_overtakes += 1
            elif prev < 0 and dx > 0:
                parts['overtaken_by'] += weights.overtaken_by
                state.n_overtaken_by += 1
        state.last_opp_del_x[oid] = dx

    # ---- Collision (terminal handled outside, but reward applied here) ----
    parts['collision'] = weights.collision if new_collision else 0.0
    if new_collision:
        state.cumulative_collisions += 1

    # ---- Lateral error quadratic ----
    parts['lat_err'] = weights.lat_err_quad * (lat_err ** 2)

    # ---- Corridor crushed ----
    parts['corridor'] = weights.corridor_crushed if (corridor_l + corridor_r) < 0.8 else 0.0

    # ---- Approach + too_close ----
    parts['approach'] = 0.0
    min_gap = 1e9
    for opp in opps:
        gap = math.hypot(opp['del_x'], opp.get('del_y', 0.0))
        oid = opp['id']
        prev_gap = state.last_opp_gap.get(oid)
        closing = (prev_gap is not None) and (gap < prev_gap)
        if gap < 25 and closing:
            parts['approach'] += weights.approach / (1 + gap)
        state.last_opp_gap[oid] = gap
        min_gap = min(min_gap, gap)

    if min_gap < 2.0:
        state.too_close_steps += 1
    else:
        state.too_close_steps = 0
    parts['too_close'] = weights.too_close if state.too_close_steps >= 10 else 0.0

    # ---- Side-by-side combat: 鼓励横向并排博弈 (典型 overtake 中段) ----
    parts['side_by_side'] = 0.0
    for opp in opps:
        if abs(opp['del_x']) < 8.0 and abs(opp.get('del_y', 0.0)) > 1.0:
            parts['side_by_side'] += weights.side_by_side
            break

    # ---- Lap PB ----
    parts['lap_pb'] = 0.0
    if new_lap_time is not None and new_lap_time > 5.0:
        if state.pb_lap is None or new_lap_time < state.pb_lap:
            state.pb_lap = new_lap_time
            parts['lap_pb'] = weights.lap_pb

    # ---- Smoothness ----
    parts['smooth'] = 0.0
    parts['geom_smooth'] = 0.0
    if state.last_action is not None and action is not None:
        diff = sum((a - b) ** 2 for a, b in zip(action, state.last_action))
        parts['smooth'] = weights.smooth * diff
        # 额外重罚 corridor L/R (idx 0,1) + lateral_bias (idx 7) 的跳变
        # 这三项决定走廊几何, 帧间跳变 → 路径跳 → 控制器猛打方向
        if len(action) >= 8 and len(state.last_action) >= 8:
            d0 = action[0] - state.last_action[0]
            d1 = action[1] - state.last_action[1]
            d7 = action[7] - state.last_action[7]
            parts['geom_smooth'] = weights.geom_smooth * (d0*d0 + d1*d1 + d7*d7)
    state.last_action = list(action) if action is not None else None

    # ---- Safety-clip penalty ----
    parts['safety'] = weights.safety_clip if safety_clipped else 0.0

    # ---- Wide corridor bonus (v23): encourage RL to NOT shrink during close engagement ----
    parts['wide_corridor'] = 0.0
    if action is not None and len(action) >= 2 and min_gap < 30.0:
        avg_margin = 0.5 * (float(action[0]) + float(action[1]))
        parts['wide_corridor'] = weights.wide_corridor * avg_margin

    total = sum(parts.values())
    return total, parts
