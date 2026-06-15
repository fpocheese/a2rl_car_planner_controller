"""Gym Env wrapping the A2RL ROS2 stack for SAC training.

Each step = 100ms (10Hz) wait, then read latest /tactical/state, build 40-d obs,
publish 9-d action to /tactical/rl_action.

Reset = avrs despawn all NPCs, teleport ego to fixed spawn, spawn NPC at
relative-dist 60m, race-control 133→0.
"""
from __future__ import annotations

import math
import os
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import gymnasium as gym
import numpy as np
import rclpy
from gymnasium import spaces

from .rl_action_bridge import (
    ACTION_BOUNDS, ACTION_DIM, RLBridgeNode, spin_bridge_in_thread,
    tanh_to_action,
)
from .reward_calc import RewardState, RewardWeights, compute_step_reward

# ---- Constants ----
# Slim Frenet-focused obs (1v1):
#   [0..5]   ego: V/80, chi, n/8, ax/20, ay/20, lap_pct
#   [6..10]  centreline curvature preview at +0,+30,+60,+100,+150 m  (×100)
#   [11..16] opp Frenet: del_s/50, del_n/8, del_v_s/30, opp_n/8, gap/50, ttc/30
#   [17..19] closing-speed bucket one-hot: stopped(≤-15) | normal(-15..-2) | matching(>-2)
#   [20..27] FSM mode one-hot (modes 0..7)
OBS_DIM = 28
CTL_HZ = 10.0
CTL_DT = 1.0 / CTL_HZ
EP_TIMEOUT_SEC = 100.0

# Curvature-preview lookahead distances (m)
CURV_PREVIEW_M = (0.0, 30.0, 60.0, 100.0, 150.0)

# Spawn (verified working)
SPAWN_X = -126.19853464465767
SPAWN_Y = -33.99481016438353
SPAWN_Z = -25.66129702943375
SPAWN_YAW = -80.0007846351562  # observer yaw (matches spawn_point.json); teleport sign-flips below

AVRS = os.path.expanduser('~/.local/bin/avrs')
NPC_NAME_PREFIX = 'rl_npc_'
N_FSM_MODES = 9  # 0..8

# ---- 1v1 场景库 —— **只训练主动超车**：NPC 必须始终在 ego 前方 ----
# 用户硬性要求 (2026-04-30)：不训练单车、不训练防守。
# Each scenario: (name, [(replay_file, rate, relative_dist)])  rel_dist 必须 > 0
# 用户要求 (2026-04-30): rate 范围 0.9-1.05，去掉 1.10 那档（太快超不动）
RESPAWN_AHEAD_DIST = 60.0  # 始终在 ego 前 60m 重 spawn
EGO_LEN = 5.3              # 车长 m（ego 与 NPC 同型）
# 用户定义 (2026-04-30 v4)：ego 车头比 opp 车头靠前即算超车成功 (head-to-head)。
# del_s = opp_s - ego_s。两车同型 → del_s < 0 即 ego 头超过 opp 头。
OVERTAKE_DS = 0.0
SCENARIOS: List[Tuple[str, List[Tuple[str, float, float]]]] = [
    ('npc_090', [('npc_70s', 0.90, RESPAWN_AHEAD_DIST)]),
    ('npc_100', [('npc_70s', 1.00, RESPAWN_AHEAD_DIST)]),
    ('npc_105', [('npc_70s', 1.05, RESPAWN_AHEAD_DIST)]),
]


def _pick_scenario(seed: Optional[int] = None) -> Tuple[str, List[Tuple[str, float, float]]]:
    rng = np.random.RandomState(seed)
    return SCENARIOS[rng.randint(0, len(SCENARIOS))]


def _run_avrs(args: List[str], timeout: float = 8.0) -> Tuple[int, str]:
    try:
        r = subprocess.run([AVRS] + args, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return -1, str(e)


def _remote_send(cmd: str) -> bool:
    """Send a command to remote_control. Tries fifo first; if write blocks
    (fifo was recreated and remote_control still holds the old deleted fd),
    falls back to /proc/<pid>/fd/0 by locating the remote_control process.
    """
    fifo = '/tmp/a2rl_remote_in'
    line = (cmd.rstrip('\n') + '\n')
    # Try fifo with short timeout (non-blocking open for write fails if no reader)
    try:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, line.encode())
            return True
        finally:
            os.close(fd)
    except OSError:
        pass
    # Fallback: locate remote_control PID and write to its stdin
    try:
        out = subprocess.check_output(
            ['pgrep', '-f', 'install/remote_control/lib/remote_control/remote_control'],
            text=True,
        ).strip().splitlines()
        for pid in out:
            try:
                with open(f'/proc/{pid.strip()}/fd/0', 'w') as f:
                    f.write(line)
                return True
            except OSError:
                continue
    except subprocess.CalledProcessError:
        pass
    return False


def _avrs_full_reset(scenario_npcs: List[Tuple[str, float, float]],
                    spawn_after_speed_ok: bool = False,
                    bridge=None) -> str:
    """Full hard reset: despawn-all + teleport ego to spawn + flag sequence.
    If spawn_after_speed_ok=True, NPC spawn is deferred to caller (after ego_V > 30).
    Otherwise spawn immediately.
    """
    log = []
    # 1) clear NPCs
    for k in range(3):
        rc, _ = _run_avrs(['vehicle-replay', 'despawn', '--all'])
        log.append(f'despawn[{k}] rc={rc}')
        time.sleep(0.4)
    # 2) first teleport ego to spawn
    tp_args = ['teleport', str(SPAWN_X), str(SPAWN_Y), str(SPAWN_Z),
               '--yaw', str(-SPAWN_YAW)]
    rc, _ = _run_avrs(tp_args)
    log.append(f'tp1 rc={rc}')
    time.sleep(2.0)
    rc, _ = _run_avrs(['race-control', '--car-flag', '255'])
    log.append(f'red rc={rc}')
    time.sleep(2.0)
    rc, _ = _run_avrs(tp_args)
    log.append(f'tp2 rc={rc}')
    time.sleep(1.0)
    # 3) yellow -> green BEFORE spawning NPC (so ego can accelerate)
    rc, _ = _run_avrs(['race-control', '--car-flag', '133'])
    log.append(f'yellow rc={rc}')
    time.sleep(1.0)
    rc, _ = _run_avrs(['race-control', '--car-flag', '0'])
    log.append(f'green rc={rc}')
    time.sleep(0.3)
    # 4) clear sticky safe_stop in controller
    ok = _remote_send('reset')
    log.append(f'reset_send={ok}')
    time.sleep(0.5)
    # 5) optionally wait for ego to reach race speed before spawning NPC
    spawned_names: List[str] = []
    if spawn_after_speed_ok and bridge is not None:
        t0 = time.time()
        while time.time() - t0 < 30.0:  # max 30s wait
            snap = bridge.snapshot()
            if snap.ego_V > 30.0:
                log.append(f'spd_ok V={snap.ego_V:.1f} after {time.time()-t0:.1f}s')
                break
            time.sleep(0.2)
        else:
            log.append(f'spd_timeout V={bridge.snapshot().ego_V:.1f}')
    # 6) spawn NPC ahead
    for i, (replay, rate, rel_dist) in enumerate(scenario_npcs[:1]):
        name = f'{NPC_NAME_PREFIX}{int(time.time()) % 100000}_{i}'
        rc, _ = _run_avrs([
            'vehicle-replay', 'spawn', replay,
            '--name', name,
            '--rate', str(rate),
            '--relative-dist', str(rel_dist),
            '--auto-start',
        ])
        log.append(f'spawn[{i}] {replay} rate={rate} d={rel_dist:+.0f} rc={rc} name={name}')
        spawned_names.append(name)
    _avrs_full_reset.last_npc_names = spawned_names  # type: ignore[attr-defined]
    return ' | '.join(log)


def _avrs_soft_respawn(scenario_npcs: List[Tuple[str, float, float]]) -> str:
    """Soft reset: ego keeps moving, just despawn-all and spawn fresh NPC ahead.
    Used when previous episode ended cleanly (overtake / v2v_lost / timeout, no crash).
    """
    log = []
    rc, _ = _run_avrs(['vehicle-replay', 'despawn', '--all'])
    log.append(f'despawn rc={rc}')
    time.sleep(0.3)
    spawned_names: List[str] = []
    for i, (replay, rate, rel_dist) in enumerate(scenario_npcs[:1]):
        name = f'{NPC_NAME_PREFIX}{int(time.time()) % 100000}_S'
        rc, _ = _run_avrs([
            'vehicle-replay', 'spawn', replay,
            '--name', name,
            '--rate', str(rate),
            '--relative-dist', str(rel_dist),
            '--auto-start',
        ])
        log.append(f'spawn {replay} rate={rate} d={rel_dist:+.0f} rc={rc} name={name}')
        spawned_names.append(name)
    _avrs_soft_respawn.last_npc_names = spawned_names  # type: ignore[attr-defined]
    return ' | '.join(log)


# 旧名字保留兼容（始终走 hard-reset 路径）
def _avrs_reset_world(scenario_npcs):
    s = _avrs_full_reset(scenario_npcs)
    _avrs_reset_world.last_npc_names = getattr(_avrs_full_reset, 'last_npc_names', [])
    return s


def _curv_at(track, s_query: float) -> float:
    """Linear-interp signed curvature at arc-length s on baseline."""
    if track is None:
        return 0.0
    s_arr = track.s
    L = float(track.track_length)
    s_w = s_query % L
    return float(np.interp(s_w, s_arr, track.Omega_z))


def _build_obs_vec(snap, last_action: np.ndarray, track=None) -> np.ndarray:
    """Pack 28-d Frenet-focused observation (1v1)."""
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    L = float(track.track_length) if track is not None else 3000.0

    # [0..5] ego state (Frenet-aligned)
    obs[0] = snap.ego_V / 80.0
    obs[1] = snap.ego_chi
    obs[2] = snap.ego_n / 8.0
    obs[3] = snap.ego_ax / 20.0
    obs[4] = snap.ego_ay / 20.0
    obs[5] = (snap.ego_s % L) / L

    # [6..10] curvature preview (赛道未来曲率)
    for i, dist in enumerate(CURV_PREVIEW_M):
        obs[6 + i] = _curv_at(track, snap.ego_s + dist) * 100.0

    # [11..16] 1v1 opponent in Frenet
    if len(snap.opps) >= 1:
        o = snap.opps[0]
        # Choose opp with smallest |del_s| (closest in arc length, wrap-safe)
        if len(snap.opps) > 1:
            o = min(snap.opps,
                    key=lambda q: abs(((q['s'] - snap.ego_s + L / 2) % L) - L / 2))
        # wrap del_s into [-L/2, L/2]
        del_s = ((o['s'] - snap.ego_s + L / 2) % L) - L / 2
        del_n = o['n'] - snap.ego_n
        del_v_s = o['V'] - snap.ego_V  # closing speed in s-direction (negative = closing)
        gap = math.hypot(del_s, del_n)
        # Time-to-contact (only meaningful when closing)
        if del_v_s < -0.1 and del_s > 0:
            ttc = del_s / max(-del_v_s, 0.01)
        else:
            ttc = 30.0
        obs[11] = del_s / 50.0
        obs[12] = del_n / 8.0
        obs[13] = del_v_s / 30.0
        # obs[14] 保留 0：用户要求不输入对手绝对位置，仅留相对态势
        obs[14] = 0.0
        obs[15] = gap / 50.0
        obs[16] = min(ttc, 30.0) / 30.0

        # [17..19] closing-speed bucket (one-hot) — 仅当对手在前 (del_s>0) 时分类
        # 慢车/停车 (del_v_s<=-15 m/s 或对手 V<5)
        # 正常车 (-15 < del_v_s <= -2)
        # 同速/逃离 (del_v_s > -2)
        if del_s > 0:
            if del_v_s <= -15.0 or o['V'] < 5.0:
                obs[17] = 1.0
            elif del_v_s <= -2.0:
                obs[18] = 1.0
            else:
                obs[19] = 1.0

    # [20..27] FSM mode one-hot
    m = snap.fsm_mode
    if 0 <= m < 8:
        obs[20 + m] = 1.0

    return np.clip(obs, -10.0, 10.0)


class A2RLTacticalEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, max_steps: int = int(EP_TIMEOUT_SEC * CTL_HZ),
                 verbose: bool = False):
        super().__init__()
        self.observation_space = spaces.Box(
            low=-10.0, high=10.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(ACTION_DIM,), dtype=np.float32)
        self.max_steps = max_steps
        self.verbose = verbose

        # ROS2
        if not rclpy.ok():
            rclpy.init()
        self.bridge = RLBridgeNode()
        self.executor, self.bridge_thread = spin_bridge_in_thread(self.bridge)

        self._reward_state = RewardState()
        self._weights = RewardWeights()
        self._step_idx = 0
        self._ep_start_t = 0.0
        self._last_action_phys = np.array(
            [0.5 * (lo + hi) for lo, hi in ACTION_BOUNDS], dtype=np.float64)
        self._off_track_count = 0

        # 加载赛道 (与 tactical_node 同一 CSV) 供曲率预览
        self.track = self._load_track()

    def _load_track(self):
        try:
            from tactical_decision.light_track_handler import LightTrackHandler
            from ament_index_python.packages import get_package_share_directory
            share = get_package_share_directory('planner_cvxopt')
            track_dir = os.path.join(share, 'config', 'tracks', 'North_Line')
            base = os.path.join(track_dir, 'BaseLine_11_15_0610115_1725_fix19_exp10.csv')
            if not os.path.isfile(base):
                # fallback: any BaseLine in dir
                for f in os.listdir(track_dir):
                    if f.startswith('BaseLine') and f.endswith('.csv'):
                        base = os.path.join(track_dir, f); break
            rl = os.path.join(track_dir, 'RaceLine_11_15_0610115_1725_fix19_exp10.csv')
            return LightTrackHandler(base, raceline_csv=rl if os.path.isfile(rl) else None)
        except Exception as e:
            print(f'[ENV] WARN: failed to load track for curvature preview: {e}')
            return None

    # --------------------------------------------------------------
    def _respawn_fresh_npc_ahead(self, reason: str):
        """Despawn ALL cars, spawn a fresh NPC at +60m ahead.
        Used for both (a) ego overtook NPC, (b) v2v lost opponent.
        """
        # 用户要求：清掉所有再生成新的，避免老车残留
        _run_avrs(['vehicle-replay', 'despawn', '--all'])
        time.sleep(0.3)
        scen_name, npcs = _pick_scenario(None)
        replay, rate, _ = npcs[0]
        new_name = f'{NPC_NAME_PREFIX}{int(time.time()) % 100000}_R'
        rc, _ = _run_avrs([
            'vehicle-replay', 'spawn', replay,
            '--name', new_name,
            '--rate', str(rate),
            '--relative-dist', str(RESPAWN_AHEAD_DIST),
            '--auto-start',
        ])
        self._cur_npc_name = new_name
        self._opp_was_ahead = False  # reset hysteresis for next overtake
        self._opp_lost_since = None
        self._last_rotate_t = time.time()
        if self.verbose:
            print(f'[ENV] respawn ({reason}) -> {new_name} '
                  f'{replay} rate={rate} d=+{RESPAWN_AHEAD_DIST:.0f} rc={rc}')

    def _rotate_npc_if_overtaken(self, snap):
        """1v1 rotation —— 用户硬性需求：始终保持前方有车。
          (a) ego 已超过当前 NPC (del_s < -10m，且之前 NPC 在前) → 重置
          (b) v2v 持续 ≥2s 无对手 (snap.opps 空) → 重置
        """
        now = time.time()
        # cooldown 防止反复 reset
        if now - getattr(self, '_last_rotate_t', 0.0) < 3.0:
            # 但仍要更新 opp_lost 计时
            if not snap.opps:
                if getattr(self, '_opp_lost_since', None) is None:
                    self._opp_lost_since = now
            else:
                self._opp_lost_since = None
            return

        # (b) v2v 丢失 —— 也算一回合结束（让 SB3 reset 重生成场景）
        if not snap.opps:
            # reset 刚结束的 grace 期内不计
            if now < getattr(self, '_reset_grace_until', 0.0):
                return
            if getattr(self, '_opp_lost_since', None) is None:
                self._opp_lost_since = now
            elif now - self._opp_lost_since > 2.0:
                if self.verbose:
                    print('[ENV] v2v lost ≥2s -> end episode')
                self._overtake_done = True  # 复用同一个终止标志
            return
        else:
            self._opp_lost_since = None

        # (a) overtake check
        o = snap.opps[0]
        del_s = o['s'] - snap.ego_s
        # wrap to [-L/2, L/2] using track length if available
        if self.track is not None:
            L = float(self.track.track_length)
            del_s = ((del_s + L / 2) % L) - L / 2
        if del_s > 2.0:
            self._opp_was_ahead = True
        # 用户定义 v4：ego 车头比 opp 车头靠前 (del_s < 0) 即超车成功
        if getattr(self, '_opp_was_ahead', False) and del_s < OVERTAKE_DS:
            self._reward_state.n_overtakes += 1
            self._overtake_done = True   # 驱动 step 里 terminate
            if self.verbose:
                print(f'[ENV] overtake! del_s={del_s:.1f}m (<={OVERTAKE_DS}m)')

    # --------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        scen_name, npcs = _pick_scenario(seed)
        self._current_scenario = scen_name

        # 决策：软重置 (续体) vs 硬重置 (传送回起点)
        # 硬重置条件：首次 reset / 上回合撞车 / 上回合出界 / ego 车速<5 且靠近起点
        snap0 = self.bridge.snapshot()
        first_reset = not getattr(self, '_has_done_initial_reset', False)
        last_crashed = bool(getattr(self, '_last_episode_crashed', False))
        ego_stuck = (snap0.ego_V < 5.0)
        need_hard = first_reset or last_crashed or ego_stuck

        if need_hard:
            log = _avrs_full_reset(npcs, spawn_after_speed_ok=True, bridge=self.bridge)
            names = getattr(_avrs_full_reset, 'last_npc_names', [])
            kind = 'HARD'
        else:
            log = _avrs_soft_respawn(npcs)
            names = getattr(_avrs_soft_respawn, 'last_npc_names', [])
            kind = 'SOFT'

        self._has_done_initial_reset = True
        self._last_episode_crashed = False
        self._cur_npc_name = names[0] if names else None
        # 重置 1v1 状态
        self._opp_was_ahead = False
        self._opp_lost_since = None
        self._last_rotate_t = time.time()
        self._overtake_done = False
        # SOFT 重置不需加速 grace；HARD 重置已在 _avrs_full_reset 里等过 V>30，允许 5s grace 防拖带
        self._reset_grace_until = time.time() + (5.0 if kind == 'HARD' else 2.0)
        if self.verbose:
            print(f'[ENV] reset[{kind}] scenario={scen_name} V0={snap0.ego_V:.1f} | {log}')
        self._reward_state = RewardState()
        # warm up — wait for fresh state
        t0 = time.time()
        while time.time() - t0 < 3.0:
            snap = self.bridge.snapshot()
            if snap.last_update_t > 0 and time.time() - snap.last_update_t < 0.5:
                break
            time.sleep(0.1)
        # consume any pending collisions/laps from previous episode
        self.bridge.consume_collisions()
        self.bridge.consume_lap()
        self._step_idx = 0
        self._ep_start_t = time.time()
        self._off_track_count = 0
        snap = self.bridge.snapshot()
        obs = _build_obs_vec(snap, self._last_action_phys, self.track)
        return obs, {}

    # --------------------------------------------------------------
    def step(self, action):
        # Map tanh → physical + safety clip
        phys = tanh_to_action(np.asarray(action, dtype=np.float64))
        # Detect clipping (compare to raw mapping)
        raw = np.array([
            ACTION_BOUNDS[i][0] + 0.5 * (max(-1.0, min(1.0, float(action[i]))) + 1.0)
            * (ACTION_BOUNDS[i][1] - ACTION_BOUNDS[i][0])
            for i in range(ACTION_DIM)
        ])
        clipped = bool(np.any(np.abs(phys - raw) > 1e-6))

        self.bridge.publish_action(phys)
        self._last_action_phys = phys

        # Wait one control tick
        time.sleep(CTL_DT)

        # Build new obs + reward
        snap = self.bridge.snapshot()
        # 1v1 rotation: if we passed the NPC, swap in a new one
        self._rotate_npc_if_overtaken(snap)
        lat_pct = self.bridge.latest_lat_pct()
        d_col, _, _ = self.bridge.consume_collisions()
        new_lap = self.bridge.consume_lap()
        new_collision = d_col > 0

        # lateral err in meters from track-handler frame ~= ego_n
        lat_err = snap.ego_n
        opp_input = []
        for o in snap.opps:
            opp_input.append({
                'id': o['id'],
                'del_x': o['s'] - snap.ego_s,
                'del_y': o['n'] - snap.ego_n,
                'V': o['V'],
            })

        r, parts = compute_step_reward(
            ego_s=snap.ego_s,
            lat_err=lat_err,
            opps=opp_input,
            corridor_l=phys[0],
            corridor_r=phys[1],
            new_collision=new_collision,
            new_lap_time=new_lap,
            action=phys.tolist(),
            safety_clipped=clipped,
            state=self._reward_state,
            weights=self._weights,
        )

        # Off-track tracking
        if abs(lat_pct) > 100.0:  # outside ribbon
            self._off_track_count += 1

        # Episode end
        # 用户要求：一次博弈 = 一回合。超车成功 / 撞车 / 出界 均终止。
        crashed = bool(new_collision) or self._off_track_count > 50
        if crashed:
            self._last_episode_crashed = True  # 下一回合 reset() 走 hard 路径
        terminated = (
            crashed
            or getattr(self, '_overtake_done', False)
        )
        truncated = (time.time() - self._ep_start_t) > EP_TIMEOUT_SEC
        self._step_idx += 1
        if self._step_idx >= self.max_steps:
            truncated = True

        obs = _build_obs_vec(snap, self._last_action_phys, self.track)
        # Outcome tag for tensorboard callback
        if terminated:
            if getattr(self, '_overtake_done', False) and not crashed:
                outcome = 'overtake'
            elif new_collision:
                outcome = 'collision'
            elif self._off_track_count > 50:
                outcome = 'off_track'
            else:
                outcome = 'v2v_lost'
        elif truncated:
            outcome = 'timeout'
        else:
            outcome = ''
        info = {
            'reward_parts': parts,
            'overtakes': self._reward_state.n_overtakes,
            'overtaken_by': self._reward_state.n_overtaken_by,
            'collisions': self._reward_state.cumulative_collisions,
            'off_track_count': self._off_track_count,
            'safety_clipped': clipped,
            'scenario': getattr(self, '_current_scenario', 'unknown'),
            'outcome': outcome,
            'crashed': crashed,
        }
        return obs, float(r), terminated, truncated, info

    # --------------------------------------------------------------
    def close(self):
        try:
            self.executor.shutdown()
        except Exception:
            pass
        try:
            self.bridge.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass
