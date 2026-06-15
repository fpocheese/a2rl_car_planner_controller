# -*- coding: utf-8 -*-
"""
A2RL Obstacle Carver v9 -- Clean rewrite for smooth, wide corridor racing.

Design Principles (v9):
  1. Ego ALWAYS inside corridor - _ensure_ego_reachable is mandatory
  2. OVERTAKE: wide corridor - opponent side to track boundary
  3. Smooth corridor transitions - temporal EMA + spatial kernel
  4. NO speed limits / caps / clamping - full V_max always
  5. High curvature (>0.03): inner-side overtake ONLY
  6. Elsewhere: wider side overtake, enlarge corridor generously
  7. Failed overtake: maintain position, <=5m gap, smooth transition

Speed control:
  FOLLOW / SHADOW use PID on s-gap, output as speed_scale hint (>=0.65).
  Path (lateral) is always solved by ACADOS OCP.

Design: NEVER modify OCP cost/constraints.  Only shape
n_left_override, n_right_override, speed_cap, speed_scale.
"""

import numpy as np
from enum import Enum, auto

from tactical_decision.tactical_action import PlannerGuidance


class CarverMode(Enum):
    OVERTAKE    = auto()
    FOLLOW      = auto()
    SHADOW      = auto()
    HOLD        = auto()
    RACELINE    = auto()
    FORCE_LEFT  = auto()
    FORCE_RIGHT = auto()
    DEFEND      = auto()
    CH8_STATIC  = auto()   # ch8: static obstacle bypass (full width + carve)


class GapPID:
    """PID controller for gap distance -> speed command."""
    def __init__(self, Kp=3.0, Ki=0.15, Kd=1.5, integral_max=30.0):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.integral_max = integral_max
        self._integral = 0.0
        self._prev_error = None

    def reset(self):
        self._integral = 0.0
        self._prev_error = None

    def compute(self, gap_target, gap_current, leader_V, dt=0.125):
        error = gap_current - gap_target
        self._integral += error * dt
        self._integral = np.clip(self._integral,
                                 -self.integral_max, self.integral_max)
        if self._prev_error is not None:
            deriv = (error - self._prev_error) / max(dt, 1e-6)
        else:
            deriv = 0.0
        self._prev_error = error
        return leader_V + self.Kp * error + self.Ki * self._integral + self.Kd * deriv


class A2RLObstacleCarver:
    """Multi-mode feasible-domain modifier.  v9: Clean, smooth, wide corridor."""

    def __init__(self, track_handler, cfg, global_planner=None):
        self.track_handler = track_handler
        self.cfg = cfg
        self.track_len = track_handler.s[-1]
        self.global_planner = global_planner

        # base offsets
        self.w_l_offset = -1.5
        self.w_r_offset = +1.5

        # common — vehicle geometry from config
        self.opp_half_w         = cfg.vehicle_width / 2.0   # 0.965m
        self.opp_half_l         = cfg.vehicle_length / 2.0  # 2.65m
        self.ego_half_w         = cfg.vehicle_width / 2.0   # 0.965m
        self.ego_half_l         = cfg.vehicle_length / 2.0  # 2.65m
        # Safety clearance (pure margin beyond vehicle extents)
        self.lateral_safety     = 2.0     # lateral safety gap [m]
        # Effective exclusion = opp_half_w + ego_half_w + lateral_safety
        #                     = 0.965 + 0.965 + 2.0 ≈ 3.93m (was 4.0m)
        self.opp_clearance      = self.ego_half_w + self.lateral_safety
        # Behind-ignore distance: opponent already well behind ego
        self.behind_ignore_s    = self.opp_half_l + self.ego_half_l + 1.0  # ≈6.3m
        self.min_corridor       = 3.0     # v16: 回退到v14值 (was 4.0)
        self.smooth_kernel_size = 7
        self.safety_s           = 50.0
        self.latch_dist         = 30.0
        self.V_max              = 80.0

        # OVERTAKE
        self.fade_start         = 35.0
        self.fade_end           = 12.0
        self.overtake_excl_min  = 3.5

        # FOLLOW
        self.follow_gap_target  = 10.0
        self.follow_gap_min     = 3.0
        self.follow_funnel_half = 1.5

        # SHADOW
        self.shadow_gap_target  = 10.0
        self.shadow_lateral_offset = 4.5   # v13: 加大偏移 (was 3.5), 引导到对手侧面
        self.shadow_base_offset = 1.5      # v16: 回退到v14值 (was 1.0)
        self.shadow_funnel_half = 2.5
        self.shadow_convergence = 35.0     # v16: 回退到v14值 (was 45)
        self.shadow_near_extra  = 5.0      # v16: 回退到v14值 (was 6.0)
        self.shadow_asym_ratio  = 0.6      # v13: 近端不对称比 — 超车侧占 60%，对手侧 40%
        self.shadow_ot_gap_thr  = 25.0    # v11: 放宽到 25m (was 20m)
        self.shadow_ot_space    = 1.5     # v11: 降到 1.5m (was 2.0m)

        # RACELINE
        self.raceline_funnel_half  = 3.0   # ±3m → 总宽6m（原2.0太窄导致OCP不可行）
        self.raceline_convergence  = 80.0

        # DEFEND — yield to outer side of upcoming turn
        self.defend_funnel_half    = 3.0   # target corridor ±3m on outer side
        self.defend_convergence    = 35.0  # converge over 35m (fast, dedicated param)
        self.defend_wall_margin    = 1.5   # margin from track wall [m]

        # PID controllers
        self._follow_pid = GapPID(Kp=2.5, Ki=0.10, Kd=2.0)
        self._shadow_pid = GapPID(Kp=2.5, Ki=0.10, Kd=2.0)

        # persistent state
        self._prev_side = {}
        self._overtake_ready = False
        self._shadow_side = None
        self._overtake_side = None
        self._prev_mode = None

        # v10: temporal smoothing state (EMA)
        # 降低 alpha 使 corridor 变化更平滑，避免模式切换时跳变
        self._prev_w_left = None
        self._prev_w_right = None
        self._ema_alpha = 0.2    # v10: 更慢的 EMA（原 0.35），需要更多帧才能收敛

    @property
    def overtake_ready(self):
        return self._overtake_ready

    @property
    def current_shadow_side(self):
        return self._shadow_side or 'left'

    @property
    def current_overtake_side(self):
        return self._overtake_side or 'left'

    # ==================================================================
    # Public entry
    # ==================================================================
    def construct_guidance(self, ego_state, opp_states, N_stages, ds,
                           mode=None, shadow_side=None, overtake_side=None,
                           prev_trajectory=None, target_opp_id=None,
                           planner_healthy=True, follow_opponents=True):
        if mode is None:
            mode = CarverMode.OVERTAKE

        if mode != self._prev_mode:
            self._follow_pid.reset()
            self._shadow_pid.reset()
            self._prev_mode = mode

        guidance = PlannerGuidance()
        self._overtake_ready = False

        s_arr = np.array([ego_state['s'] + i * ds for i in range(N_stages)])
        s_wrapped = s_arr % self.track_len

        # 使用 RaceLine Sref 坐标系下的赛道边界进行插值
        # （ego_s 来自 C++ GetState()，本身就是 RaceLine Sref 坐标）
        rl_s = self.track_handler.raceline_s
        rl_len = self.track_handler.raceline_track_length
        s_wrapped_rl = s_arr % rl_len

        w_l_base = (np.interp(s_wrapped_rl, rl_s,
                              self.track_handler.rl_w_tr_left,
                              period=rl_len) + self.w_l_offset)
        w_r_base = (np.interp(s_wrapped_rl, rl_s,
                              self.track_handler.rl_w_tr_right,
                              period=rl_len) + self.w_r_offset)

        w_left = w_l_base.copy()
        w_right = w_r_base.copy()

        if (prev_trajectory is not None
                and len(prev_trajectory.get('t', [])) == N_stages):
            t_arr = np.array(prev_trajectory['t'])
        else:
            V_est = max(ego_state['V'], 10.0)
            t_arr = np.array([i * ds / V_est for i in range(N_stages)])

        max_v_node = N_stages
        for i in range(N_stages):
            if t_arr[i] > self.cfg.planning_horizon:
                max_v_node = i
                break

        # ---- Mode dispatch ----
        if mode == CarverMode.FOLLOW:
            speed_cap, speed_scale = self._mode_follow(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, target_opp_id)
        elif mode == CarverMode.SHADOW:
            side = shadow_side if shadow_side else self._decide_shadow_side(
                ego_state, opp_states)
            self._shadow_side = side
            speed_cap, speed_scale = self._mode_shadow(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, side, target_opp_id)
        elif mode == CarverMode.HOLD:
            side = overtake_side if overtake_side else self._overtake_side
            if side is None:
                side = self._decide_shadow_side(ego_state, opp_states)
            self._shadow_side = side
            self._overtake_side = side
            speed_cap, speed_scale = self._mode_hold(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, N_stages, side, target_opp_id)
        elif mode == CarverMode.RACELINE:
            speed_cap, speed_scale = self._mode_raceline(
                ego_state, s_arr, s_wrapped,
                w_left, w_right, w_l_base, w_r_base, N_stages)
            # v10: RACELINE 模式下也检查超车窗口，让 FSM 能直接切 OVERTAKE
            if opp_states:
                ot_side = shadow_side or overtake_side or self._decide_shadow_side(
                    ego_state, opp_states)
                target = self._find_target(ego_state, opp_states, target_opp_id)
                self._overtake_ready = self._check_overtake_window(
                    ego_state, target, ot_side)
        elif mode in (CarverMode.FORCE_LEFT, CarverMode.FORCE_RIGHT):
            force_side = 'left' if mode == CarverMode.FORCE_LEFT else 'right'
            speed_cap, speed_scale = self._mode_force_side(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, N_stages, force_side, follow_opponents)
        elif mode == CarverMode.DEFEND:
            # defend_side is passed via shadow_side parameter
            def_side = shadow_side if shadow_side else 'right'
            speed_cap, speed_scale = self._mode_defend(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, N_stages, def_side)
        elif mode == CarverMode.CH8_STATIC:
            ot_side = overtake_side if overtake_side else \
                self._decide_overtake_side(ego_state, opp_states)
            # CH8: 右边界 base 从 +1.5 放宽到 -1.0 (多给 2.5m 绕行空间)
            # 左边界保持 -1.5 收紧不变 (不动 w_l_base)
            w_r_base -= 2.5    # w_r_offset(+1.5) → 实际 -1.0
            speed_cap, speed_scale = self._mode_ch8_static(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, N_stages, ot_side)
        else:  # OVERTAKE
            side = overtake_side if overtake_side else self._decide_overtake_side(
                ego_state, opp_states)
            self._overtake_side = side
            speed_cap, speed_scale = self._mode_overtake(
                ego_state, opp_states, s_arr, s_wrapped, t_arr,
                w_left, w_right, w_l_base, w_r_base,
                max_v_node, side)

        # v9: NO public safety layer (removed _apply_all_opp_safety)
        # v9: NO proximity speed limit (removed _proximity_speed_limit)

        is_force_mode = mode in (CarverMode.FORCE_LEFT, CarverMode.FORCE_RIGHT)
        is_ch8_mode = (mode == CarverMode.CH8_STATIC)

        # Spatial smoothing: CH8 跳过! kernel_size=7 的滑窗平均会把方形挖除
        # (纵向仅覆盖 2-3 个节点) 稀释到原来的 ~30%, 导致排斥区大小不稳定
        if not is_ch8_mode:
            w_left, w_right = self._smooth_boundaries(w_left, w_right, N_stages)

        # Feasibility
        w_left, w_right = self._ensure_feasibility(
            w_left, w_right, w_l_base, w_r_base, N_stages)

        # Ego reachable: 跳过 FORCE 模式（否则会撑开半赛道走廊）
        # 跳过 CH8 模式（否则会撑开 corridor 撤销排斥区，导致 ego 贴着对手走）
        if not is_force_mode and not is_ch8_mode:
            w_left, w_right = self._ensure_ego_reachable(
                ego_state, w_left, w_right, w_l_base, w_r_base, N_stages)

        # Temporal EMA: 跳过 FORCE / CH8 模式（直接使用目标走廊，不做时间平滑）
        if not is_force_mode and not is_ch8_mode:
            w_left, w_right = self._temporal_smooth(w_left, w_right, N_stages, mode)
        else:
            # FORCE / CH8 模式不 EMA，但更新 prev 缓存以免退出后跳变
            self._prev_w_left = w_left.copy()
            self._prev_w_right = w_right.copy()

        guidance.n_left_override = w_left
        guidance.n_right_override = w_right
        guidance.speed_cap = speed_cap
        guidance.speed_scale = speed_scale
        guidance.terminal_V_guess = -1.0
        return guidance

    # ==================================================================
    # Heading-aware projection: compute opponent's actual footprint
    # ==================================================================
    def _heading_aware_projection(self, opp_chi):
        """Compute opponent's projected half-extents in Frenet frame.

        When opp_chi ≈ 0 the car is aligned with the track and the
        projection equals the normal half-width / half-length.
        When opp_chi ≈ ±π/2 the car is sideways and the lateral
        projection grows to half the vehicle length.

        Returns (proj_half_n, proj_half_s) — half-extents in lateral
        and longitudinal Frenet directions, including safety margin.
        """
        veh_L = self.cfg.vehicle_length   # 5.30m
        veh_W = self.cfg.vehicle_width    # 1.93m
        abs_sin = abs(np.sin(opp_chi))
        abs_cos = abs(np.cos(opp_chi))
        proj_n = veh_L * abs_sin + veh_W * abs_cos
        proj_s = veh_L * abs_cos + veh_W * abs_sin
        proj_half_n = max(proj_n / 2.0, self.opp_half_w)
        proj_half_s = max(proj_s / 2.0, self.opp_half_l)
        return proj_half_n, proj_half_s

    def _dynamic_safety_s(self, ego_V, opp_V):
        """Compute closing-speed-aware longitudinal influence range.

        Higher closing speed → larger range so the corridor starts
        modifying earlier, giving ego more time to manoeuvre.
        """
        closing_V = max(ego_V - opp_V, 0.0)
        dynamic = closing_V * closing_V / (2.0 * 6.0) + self.safety_s
        return float(np.clip(dynamic, self.safety_s, 120.0))

    # ==================================================================
    def _cosine_fade(self, ds_abs, safety_s):
        if ds_abs >= safety_s:
            return 0.0
        return np.cos(ds_abs / safety_s * (np.pi / 2.0)) ** 3

    def _startup_ramp(self, i):
        if i < 15:
            return 0.4 + 0.6 * (i / 15.0)
        return 1.0

    # ==================================================================
    # OVERTAKE -- v10: wide corridor on pass side + funnel transition
    # ==================================================================
    def _mode_overtake(self, ego_state, opp_states, s_arr, s_wrapped,
                       t_arr, w_left, w_right, w_l_base, w_r_base,
                       max_v_node, overtake_side=None):
        """v10 OVERTAKE:
        - 漏斗式过渡: 近端（前30m）保持宽corridor（类似RACELINE），
          远端逐渐收窄到超车侧，避免从RACELINE切来时corridor跳变
        - Exclusion side: push boundary away from opponent
        - Pass side: KEEP WIDE -- full track width for passing
        """
        speed_cap = self.V_max
        speed_scale = 1.0
        ds_per_node = (s_arr[1] - s_arr[0]) if len(s_arr) > 1 else 2.0

        ego_V = ego_state.get('V', 30.0)

        for opp_idx, opp in enumerate(opp_states):
            opp_s_traj, opp_n_traj = self._predict_opp(opp, t_arr, max_v_node)
            actual_opp_s = opp['s']
            actual_opp_n = opp['n']

            opp_chi = opp.get('chi', 0.0)
            proj_half_n, proj_half_s = self._heading_aware_projection(opp_chi)
            opp_V = opp.get('V', 0.0)
            eff_safety_s = self._dynamic_safety_s(ego_V, opp_V)
            eff_behind_s = max(self.behind_ignore_s, proj_half_s + self.ego_half_l + 1.0)

            for i in range(max_v_node):
                ds_raw = self._signed_gap(opp_s_traj[i], s_arr[i])
                ds_actual = self._signed_gap(actual_opp_s, s_arr[i])
                if abs(ds_actual) < abs(ds_raw) and abs(ds_actual) < 15.0:
                    use_opp_n = actual_opp_n
                    use_ds_raw = ds_actual
                else:
                    use_opp_n = opp_n_traj[i]
                    use_ds_raw = ds_raw

                if use_ds_raw < -eff_behind_s:
                    continue
                ds_abs = abs(use_ds_raw)
                if ds_abs >= eff_safety_s:
                    continue

                ds_from_ego = i * ds_per_node
                funnel_ramp = min(ds_from_ego / 40.0, 1.0)

                fade = self._cosine_fade(ds_abs, eff_safety_s)
                fade *= self._startup_ramp(i)
                fade *= funnel_ramp

                excl_n = (proj_half_n + self.opp_clearance) * fade
                if ds_abs < 15.0 and funnel_ramp > 0.5:
                    s_node = s_arr[i] % self.track_len
                    local_curv = abs(float(np.interp(
                        s_node, self.track_handler.s,
                        self.track_handler.Omega_z,
                        period=self.track_len)))
                    curv_extra = min(local_curv / 0.05, 1.0) * 1.0
                    excl_n = max(excl_n, (self.overtake_excl_min + curv_extra) * funnel_ramp)

                opp_n = use_opp_n

                if overtake_side == 'left':
                    new_r = opp_n + excl_n
                    if new_r > w_right[i]:
                        w_right[i] = new_r
                else:
                    new_l = opp_n - excl_n
                    if new_l < w_left[i]:
                        w_left[i] = new_l

            self._prev_side[opp_idx] = overtake_side

        return speed_cap, speed_scale

    # ==================================================================
    # FOLLOW
    # ==================================================================
    def _mode_follow(self, ego_state, opp_states, s_arr, s_wrapped,
                     t_arr, w_left, w_right, w_l_base, w_r_base,
                     max_v_node, target_opp_id=None):
        target = self._find_target(ego_state, opp_states, target_opp_id)
        if target is None:
            return self.V_max, 1.0

        leader_V = target.get('V', 30.0)
        opp_s_traj, opp_n_traj = self._predict_opp(target, t_arr, max_v_node)
        gap_current = self._signed_gap(target['s'], ego_state['s'])

        speed_scale = 1.0
        if gap_current > 0:
            speed_cmd = self._follow_pid.compute(
                self.follow_gap_target, gap_current, leader_V)
            speed_scale = float(np.clip(speed_cmd / max(self.V_max, 1.0),
                                        0.65, 1.0))
        speed_cap = self.V_max

        for i in range(max_v_node):
            opp_s_pred = opp_s_traj[i]
            opp_n_pred = opp_n_traj[i]
            ds_raw = self._signed_gap(opp_s_pred, s_arr[i])
            if ds_raw < -self.behind_ignore_s:
                continue
            ds_abs = abs(ds_raw)
            if ds_abs >= self.safety_s:
                continue
            fade = self._cosine_fade(ds_abs, self.safety_s)
            fade *= self._startup_ramp(i)
            corridor_half = self.follow_funnel_half + (1.0 - fade) * 5.0
            w_left[i] = min(w_left[i], opp_n_pred + corridor_half)
            w_right[i] = max(w_right[i], opp_n_pred - corridor_half)

        return speed_cap, speed_scale

    # ==================================================================
    # SHADOW  -- v11: funnel-style corridor (smooth RACELINE→SHADOW)
    # ==================================================================
    def _mode_shadow(self, ego_state, opp_states, s_arr, s_wrapped,
                     t_arr, w_left, w_right, w_l_base, w_r_base,
                     max_v_node, shadow_side='left',
                     target_opp_id=None):
        """v11 SHADOW: funnel corridor similar to RACELINE but target
        lateral position is offset toward the overtake side.

        Design:
          - Near ego (front of horizon): corridor wide, nearly identical
            to RACELINE → zero jump on RACELINE→SHADOW transition.
          - Far from ego: corridor converges to shadow target position
            (raceline_n + offset toward shadow_side).
          - Additionally: opponent exclusion zone overlaid for safety.
          - Speed: PID gap control to maintain shadow distance.

        Shadow target = raceline_n + sign * shadow_lateral_offset
        This puts the ego on the preferred overtake side while tracking
        at a safe distance behind the opponent.
        """
        target = self._find_target(ego_state, opp_states, target_opp_id)
        if target is None:
            return self.V_max, 1.0

        leader_V = target.get('V', 30.0)
        opp_s_traj, opp_n_traj = self._predict_opp(target, t_arr, max_v_node)
        gap_current = self._signed_gap(target['s'], ego_state['s'])
        sign = 1.0 if shadow_side == 'left' else -1.0

        speed_scale = 1.0
        if gap_current > 0:
            speed_cmd = self._shadow_pid.compute(
                self.shadow_gap_target, gap_current, leader_V)
            speed_scale = float(np.clip(speed_cmd / max(self.V_max, 1.0),
                                        0.65, 1.0))
        speed_cap = self.V_max

        # ---- Part 1: Funnel corridor converging to shadow target ----
        # v13 redesign:
        #   - target_n has a BASE offset even at ego position (conv_fade=0),
        #     so the corridor centre is always shifted toward the overtake side.
        #   - The corridor is ASYMMETRIC: wider toward the overtake side,
        #     narrower toward the opponent side.  This gently but persistently
        #     steers the OCP solution toward the overtake side without any
        #     sudden jumps.
        #   - Convergence is faster (50m) so the corridor tightens sooner.
        rl_len = self.track_handler.raceline_track_length
        s_wrapped_rl = s_arr % rl_len
        rl_n = np.interp(s_wrapped_rl,
                         self.track_handler.raceline_s,
                         self.track_handler.raceline_n,
                         period=rl_len)

        ds_per_node = (s_arr[1] - s_arr[0]) if len(s_arr) > 1 else 2.0
        shadow_convergence = self.shadow_convergence  # 50m

        for i in range(len(s_arr)):
            ds_from_ego = i * ds_per_node

            # Cosine³ convergence: near=wide, far=narrow to target
            if ds_from_ego >= shadow_convergence:
                conv_fade = 1.0
            else:
                conv_fade = self._cosine_fade(
                    shadow_convergence - ds_from_ego,
                    shadow_convergence)
            conv_fade *= self._startup_ramp(i)

            # v13: Shadow target = raceline + base_offset + (full_offset - base) * conv
            # Near ego (conv_fade≈0): target_n = rl_n + sign * base_offset (1.5m)
            # Far (conv_fade=1):      target_n = rl_n + sign * full_offset (4.5m)
            offset_n = self.shadow_base_offset + \
                       (self.shadow_lateral_offset - self.shadow_base_offset) * conv_fade
            target_n = rl_n[i] + sign * offset_n

            # v13: ASYMMETRIC corridor — wider on overtake side, narrower on opp side
            # Total half-width shrinks with convergence (same as before)
            total_half = self.shadow_funnel_half + (1.0 - conv_fade) * self.shadow_near_extra
            # Split: overtake side gets asym_ratio (60%), opp side gets (40%)
            half_pass = total_half * (self.shadow_asym_ratio / 0.5)     # ×1.2
            half_opp  = total_half * ((1.0 - self.shadow_asym_ratio) / 0.5)  # ×0.8

            if sign > 0:  # shadow_side = 'left': pass side = left
                w_left[i]  = min(w_left[i],  target_n + half_pass)
                w_right[i] = max(w_right[i], target_n - half_opp)
            else:          # shadow_side = 'right': pass side = right
                w_left[i]  = min(w_left[i],  target_n + half_opp)
                w_right[i] = max(w_right[i], target_n - half_pass)

        # ---- Part 2: Opponent exclusion overlay (heading + closing-speed aware) ----
        ego_V = ego_state.get('V', 30.0)
        opp_chi = target.get('chi', 0.0)
        proj_half_n, proj_half_s = self._heading_aware_projection(opp_chi)
        opp_V = target.get('V', 0.0)
        eff_safety_s = self._dynamic_safety_s(ego_V, opp_V)
        eff_behind_s = max(self.behind_ignore_s, proj_half_s + self.ego_half_l + 1.0)

        for i in range(max_v_node):
            opp_s_pred = opp_s_traj[i]
            opp_n_pred = opp_n_traj[i]
            ds_raw = self._signed_gap(opp_s_pred, s_arr[i])
            if ds_raw < -eff_behind_s:
                continue
            ds_abs = abs(ds_raw)
            if ds_abs >= eff_safety_s:
                continue

            ds_from_ego = i * ds_per_node
            funnel_ramp = min(ds_from_ego / 30.0, 1.0)

            fade = self._cosine_fade(ds_abs, eff_safety_s)
            fade *= self._startup_ramp(i)
            fade *= funnel_ramp

            if ds_abs < 15.0 and funnel_ramp > 0.3:
                s_node = s_arr[i] % self.track_len
                local_curv = abs(float(np.interp(
                    s_node, self.track_handler.s,
                    self.track_handler.Omega_z,
                    period=self.track_len)))
                curv_extra = min(local_curv / 0.05, 1.0) * 1.0
                safety_excl = max(
                    (proj_half_n + self.opp_clearance) * fade,
                    (self.overtake_excl_min + curv_extra) * funnel_ramp)

                if shadow_side == 'left':
                    # Push right boundary away (ego passes on left)
                    w_right[i] = max(w_right[i], opp_n_pred + safety_excl)
                else:
                    # Push left boundary away (ego passes on right)
                    w_left[i] = min(w_left[i], opp_n_pred - safety_excl)

        self._overtake_ready = self._check_overtake_window(
            ego_state, target, shadow_side)

        return speed_cap, speed_scale

    # ==================================================================
    # HOLD -- v9.3: light corridor, rely on C++ PI for gap control
    # ==================================================================
    def _mode_hold(self, ego_state, opp_states, s_arr, s_wrapped,
                   t_arr, w_left, w_right, w_l_base, w_r_base,
                   max_v_node, N_stages, side, target_opp_id=None):
        """HOLD: raceline corridor + lightweight opponent exclusion.

        v9.3 philosophy — anti-collision comes from C++ PI speed control,
        NOT from corridor squeezing.  The carver keeps corridor wide
        (same as RACELINE) so the planner has full path freedom and
        doesn't get pushed into infeasible OCP.  Only a gentle exclusion
        is overlaid using the locked *side* direction.

        v9.3 changes vs v9.2:
          - Remove min_excl guarantee for near nodes (no longer needed,
            PI handles gap).
          - hold_gap_target 8→6m (match C++ follow_gap, avoid pulling
            too far).
          - speed_scale floor back to 0.65 (C++ speed_scale unused anyway).
          - Keep side-locked exclusion direction (good v9.2 fix).
        """
        target = self._find_target(ego_state, opp_states, target_opp_id)
        if target is None:
            return self._mode_raceline(
                ego_state, s_arr, s_wrapped,
                w_left, w_right, w_l_base, w_r_base, N_stages)

        leader_V = target.get('V', 30.0)
        gap_current = self._signed_gap(target['s'], ego_state['s'])

        # Raceline corridor as base (wide, same as pure RACELINE mode)
        speed_cap, speed_scale = self._mode_raceline(
            ego_state, s_arr, s_wrapped,
            w_left, w_right, w_l_base, w_r_base, N_stages)

        # Lightweight opponent exclusion overlay (heading + closing-speed aware)
        ego_n_now = ego_state.get('n', 0.0)
        ego_V = ego_state.get('V', 30.0)
        for opp in opp_states:
            opp_s_pred, opp_n_pred = self._predict_opp(opp, t_arr, max_v_node)
            opp_n_now = opp.get('n', 0.0)

            opp_chi = opp.get('chi', 0.0)
            proj_half_n, proj_half_s = self._heading_aware_projection(opp_chi)
            opp_V = opp.get('V', 0.0)
            eff_safety_s = self._dynamic_safety_s(ego_V, opp_V)
            eff_behind_s = max(self.behind_ignore_s, proj_half_s + self.ego_half_l + 1.0)

            if side == 'left':
                ego_is_left = True
            elif side == 'right':
                ego_is_left = False
            else:
                ego_is_left = (ego_n_now > opp_n_now)

            for i in range(max_v_node):
                ds_raw = self._signed_gap(opp_s_pred[i], s_arr[i])
                if ds_raw < -eff_behind_s:
                    continue
                ds_abs = abs(ds_raw)
                if ds_abs >= eff_safety_s:
                    continue
                fade = self._cosine_fade(ds_abs, eff_safety_s)
                fade *= self._startup_ramp(i)
                excl = (proj_half_n + self.opp_clearance) * fade

                if ds_abs < 15.0:
                    s_node = s_arr[i] % self.track_len
                    local_curv = abs(float(np.interp(
                        s_node, self.track_handler.s,
                        self.track_handler.Omega_z,
                        period=self.track_len)))
                    curv_extra = min(local_curv / 0.05, 1.0) * 1.0
                    excl = max(excl, self.overtake_excl_min + curv_extra)

                if ego_is_left:
                    w_right[i] = max(w_right[i], opp_n_pred[i] + excl)
                else:
                    w_left[i] = min(w_left[i], opp_n_pred[i] - excl)

        # PID speed hint — gap target matches C++ follow_gap (6m)
        hold_gap_target = 6.0
        speed_cmd = self._follow_pid.compute(
            hold_gap_target, gap_current, leader_V)
        speed_scale = float(np.clip(speed_cmd / max(self.V_max, 1.0),
                                    0.65, 1.0))
        speed_cap = self.V_max

        self._overtake_ready = self._check_overtake_window(
            ego_state, target, side)

        return speed_cap, speed_scale

    # ==================================================================
    # RACELINE
    # ==================================================================
    def _mode_raceline(self, ego_state, s_arr, s_wrapped,
                       w_left, w_right, w_l_base, w_r_base, N_stages):
        """RACELINE mode: funnel corridor converging to raceline (n≈0).

        Near ego (front of horizon): corridor is wide, allowing the planner
        freedom to manoeuvre from its current position.
        Far from ego (end of horizon): corridor narrows to ±raceline_funnel_half
        around the raceline centre (n=0 in RaceLine Sref), guiding the
        planner back onto the optimal racing line.

        Convergence shape: cosine³ fade over raceline_convergence metres.
        """
        speed_cap = self.V_max
        speed_scale = 1.0

        # RaceLine Sref 坐标系下 raceline 的 n 坐标
        # (在 RaceLine Sref 中，raceline 就是参考线，n≈0；
        #  但 raceline_n 存的是 L 列，有些赛道可能不严格为零)
        rl_len = self.track_handler.raceline_track_length
        s_wrapped_rl = s_arr % rl_len
        rl_n = np.interp(s_wrapped_rl,
                         self.track_handler.raceline_s,
                         self.track_handler.raceline_n,
                         period=rl_len)

        ds_per_node = (s_arr[1] - s_arr[0]) if N_stages > 1 else 2.0

        for i in range(N_stages):
            ds_from_ego = i * ds_per_node

            # 渐进收缩：近端宽(±funnel_half+8m)，远端窄(±funnel_half)
            if ds_from_ego >= self.raceline_convergence:
                fade = 1.0
            else:
                fade = self._cosine_fade(
                    self.raceline_convergence - ds_from_ego,
                    self.raceline_convergence)
            fade *= self._startup_ramp(i)

            corridor_half = self.raceline_funnel_half + (1.0 - fade) * 8.0
            w_left[i]  = min(w_left[i],  rl_n[i] + corridor_half)
            w_right[i] = max(w_right[i], rl_n[i] - corridor_half)

        return speed_cap, speed_scale

    # ==================================================================
    # CH8_STATIC -- static obstacle bypass v5 (heading-aware + closing-speed)
    # ==================================================================
    def _mode_ch8_static(self, ego_state, opp_states, s_arr, s_wrapped,
                         t_arr, w_left, w_right, w_l_base, w_r_base,
                         max_v_node, N_stages, overtake_side='left'):
        """CH8 static obstacle mode — v6 (heading-aware + closing-speed + local boundary).

        v6 改进 (相比 v5):
          - 边界策略: 不再一进入 CH8 就全局放大边界
            * 左边界: 保持正常的 -1.5m 收紧 (安全贴墙)
            * 右边界 base: 从 +1.5m 收紧改为 -1.0m 放宽 (dispatch 中处理)
            * 仅在对手附近 (fade_ahead 范围内) 进一步局部放宽绕行侧边界

        核心机制:
          1. 航向感知投影: 利用 opp_chi (Frenet heading error) 精确计算
             对手车辆在 n 方向和 s 方向的真实占据尺寸。
          2. 逼近速度决策: 根据 closing_speed = ego_V - opp_V 决定
             提前多远开始修改 corridor 和减速强度。
          3. 局部边界放宽: 仅在对手纵向影响范围内, 对绕行侧边界额外放宽。
        """
        speed_cap = self.V_max
        speed_scale = 1.0

        # --- 车辆基本尺寸 ---
        veh_L = self.cfg.vehicle_length   # 5.30m
        veh_W = self.cfg.vehicle_width    # 1.93m
        safety_margin = 0.5               # 安全裕度 [m]

        # --- 逼近速度计算 ---
        ego_V = ego_state.get('V', 30.0)
        target = self._find_target(ego_state, opp_states)

        if target is not None:
            opp_V = target.get('V', 0.0)
            closing_speed = max(ego_V - opp_V, 0.0)  # 接近速度 [m/s]
            gap = self._signed_gap(target['s'], ego_state['s'])

            # --- 基于逼近速度的减速策略 ---
            # 目标: 在到达对手 safe_pass_dist 之前, 速度降到 safe_pass_speed
            # safe_pass_speed: 弯道通过速度, 基于曲率
            s_opp = target['s'] % self.track_len
            s_look = np.linspace(s_opp - 30.0, s_opp + 30.0, 10) % self.track_len
            curv_vals = np.abs(np.interp(s_look, self.track_handler.s,
                                         self.track_handler.Omega_z,
                                         period=self.track_len))
            max_curv = float(np.max(curv_vals))

            # 高曲率弯 → 通过速度更低 (曲率>0.03时约12m/s, 直道18m/s)
            safe_pass_speed = max(8.0, min(18.0, 18.0 - max_curv * 200.0))

            # 需要多少距离从当前速度减到 safe_pass_speed
            # d = (V² - V_pass²) / (2 * a_comfort)
            comfort_decel = 8.0   # 舒适减速度 [m/s²] (0.8g, 赛车可接受)
            if ego_V > safe_pass_speed:
                brake_dist = (ego_V**2 - safe_pass_speed**2) / (2.0 * comfort_decel)
            else:
                brake_dist = 0.0
            # 额外留 20m 作为安全缓冲
            action_dist = brake_dist + 20.0

            # speed_scale: 基于到对手的距离和逼近速度
            if gap > 0:
                if gap < 20.0:
                    # 非常近: 强制低速
                    speed_scale = 0.25
                elif gap < action_dist:
                    # 在减速区间内: 线性插值
                    # gap = action_dist 时 scale=1.0, gap=20m 时 scale=0.25
                    speed_scale = float(np.clip(
                        0.25 + 0.75 * (gap - 20.0) / max(action_dist - 20.0, 1.0),
                        0.25, 1.0))
                # else: speed_scale = 1.0, 距离够远不需要减速

        # --- 核心: 对每个对手, 用航向信息计算真实投影后挖掉 ---
        for opp in opp_states:
            opp_s = opp['s']
            opp_n = opp.get('n', 0.0)
            opp_V_i = opp.get('V', 0.0)
            opp_chi = opp.get('chi', 0.0)  # Frenet heading error [rad]

            # === 航向感知投影 ===
            # opp_chi = wrapToPi(opp_yaw_enu - Aref_at_opp)  -- Frenet heading error
            #   chi ≈ 0: 对手沿赛道方向, chi ≈ ±π/2: 对手横着
            # 两条数据源 (simulator / lidar) 的 target.yaw 都是对手绝对 NED heading,
            # C++ 变换链 NED→ENU→chi 始终有效, 无需退回保守估计
            abs_sin_chi = abs(np.sin(opp_chi))
            abs_cos_chi = abs(np.cos(opp_chi))
            proj_n = veh_L * abs_sin_chi + veh_W * abs_cos_chi  # 横向投影
            proj_s = veh_L * abs_cos_chi + veh_W * abs_sin_chi  # 纵向投影

            # 加安全裕度 + ego 车宽
            excl_half_n = proj_n / 2.0 + self.ego_half_w + safety_margin
            excl_half_s = proj_s / 2.0 + 3.0  # 纵向多留 3m 冗余

            # === 逼近速度决定纵向影响范围 ===
            closing_V = max(ego_V - opp_V_i, 0.0)
            # 高速逼近时, corridor 修改的前方范围更大
            # 最小 30m, 最大 120m (150kph 逼近时约 100m)
            fade_ahead = float(np.clip(
                closing_V * closing_V / (2.0 * 5.0) + 30.0,
                30.0, 120.0))

            # 决定 ego 走哪一侧: 直接使用 FSM 传入的 overtake_side
            # (由 _decide_overtake_side 根据曲率/空间综合决定, 不在此重新判断)
            ego_goes_left = (overtake_side == 'left')

            for i in range(N_stages):
                ds_raw = self._signed_gap(opp_s, s_arr[i])

                # 纵向范围: 后方 excl_half_s 到前方 (excl_half_s + fade_ahead)
                if ds_raw < -excl_half_s or ds_raw > excl_half_s + fade_ahead:
                    continue

                # ---------- 两种衰减 ----------
                # block_fade : 封堵 (把对手侧边界推到排斥区外)
                #              只在对手附近 ±30m 范围生效, 远处不需要封堵
                # guide_fade : 引导 (放宽绕行侧边界, 让 ego 提前变道)
                #              用 fade_ahead (30-120m), 提前给 ego 变道空间
                block_range = 30.0  # 封堵的最大前向衰减距离

                if abs(ds_raw) <= excl_half_s:
                    # 在障碍物正上方: 两个 fade 都是 1.0
                    block_fade = 1.0
                    guide_fade = 1.0
                elif ds_raw > excl_half_s:
                    # 节点在 ego 侧 (ego→opp 之间, ds_raw > 0)
                    dist_from_excl = ds_raw - excl_half_s
                    block_fade = max(0.0, 1.0 - dist_from_excl / block_range)
                    guide_fade = max(0.0, 1.0 - dist_from_excl / fade_ahead)
                else:
                    # 在对手前方 (过了对手, ds_raw < 0): 不封堵也不引导
                    block_fade = 0.0
                    guide_fade = 0.0

                if guide_fade < 0.01 and block_fade < 0.01:
                    continue

                # 当前节点的挖除半宽 (用 block_fade)
                excl_w = excl_half_n * block_fade

                # --- 局部边界放宽: 用 guide_fade 控制, 远处衰减引导变道 ---
                boundary_relax = 1.5 * guide_fade  # 最大放宽 1.5m (抵消 w_l_offset)

                # --- 封堵: 确保 ego 只能从一侧通过 ---
                if ego_goes_left:
                    # ego 走左侧 → 右边界推到对手左边缘外 (封堵右侧)
                    if block_fade > 0.01:
                        block_r = opp_n + excl_w
                        if block_r > w_right[i]:
                            w_right[i] = block_r
                    # 绕行侧 (左) 局部放宽, 给 ego 更多空间
                    if boundary_relax > 0.01:
                        w_left[i] = min(w_left[i] + boundary_relax,
                                        w_l_base[i] + boundary_relax)
                else:
                    # ego 走右侧 → 左边界拉到对手右边缘外 (封堵左侧)
                    if block_fade > 0.01:
                        block_l = opp_n - excl_w
                        if block_l < w_left[i]:
                            w_left[i] = block_l
                    # 绕行侧 (右) 局部放宽 — 右边界 base 已在 dispatch 中
                    # 从 +1.5 放宽到 -1.0, 此处再额外局部放宽
                    if boundary_relax > 0.01:
                        w_right[i] = max(w_right[i] - boundary_relax,
                                         w_r_base[i] - boundary_relax)

        return speed_cap, speed_scale

    # ==================================================================
    # DEFEND -- v12: yield to one side, let pursuer pass on the other
    # ==================================================================
    def _mode_defend(self, ego_state, opp_states, s_arr, s_wrapped,
                     t_arr, w_left, w_right, w_l_base, w_r_base,
                     max_v_node, N_stages, defend_side='right'):
        """DEFEND mode: funnel corridor converging to half-track.

        defend_side = the side ego moves TO.
        Example (defend_side='right'):
          - Near ego (funnel mouth): left=left_wall, right=right_wall (full width)
          - Far (converged):         left=centreline(n=0), right=right_wall
          The left boundary funnels from left_wall → centreline over
          defend_convergence metres. Right boundary stays at the wall.
          This pushes ego into the right half, freeing the left for the pursuer.

        Example (defend_side='left'):
          - Converged: left=left_wall, right=centreline(n=0)
          The right boundary funnels from right_wall → centreline.
        """
        speed_cap = self.V_max
        speed_scale = 1.0

        rl_len = self.track_handler.raceline_track_length
        s_wrapped_rl = s_arr % rl_len

        # Track boundaries at each node
        w_l_track = np.interp(s_wrapped_rl,
                              self.track_handler.raceline_s,
                              self.track_handler.rl_w_tr_left,
                              period=rl_len) + self.w_l_offset
        w_r_track = np.interp(s_wrapped_rl,
                              self.track_handler.raceline_s,
                              self.track_handler.rl_w_tr_right,
                              period=rl_len) + self.w_r_offset

        ds_per_node = (s_arr[1] - s_arr[0]) if N_stages > 1 else 2.0

        # Centreline n coordinate (in RaceLine Sref, typically ≈ 0)
        rl_n = np.interp(s_wrapped_rl,
                         self.track_handler.raceline_s,
                         self.track_handler.raceline_n,
                         period=rl_len)

        for i in range(N_stages):
            ds_from_ego = i * ds_per_node

            # Convergence fade: 0 at ego → 1 at defend_convergence
            if ds_from_ego >= self.defend_convergence:
                fade = 1.0
            else:
                fade = self._cosine_fade(
                    self.defend_convergence - ds_from_ego,
                    self.defend_convergence)
            fade *= self._startup_ramp(i)

            # centreline = n ≈ 0 (the dividing line between left/right half)
            centre_n = float(rl_n[i])

            if defend_side == 'right':
                # Right boundary: always the right wall (keep full access)
                new_right = w_r_track[i]
                # Left boundary: funnels from left_wall → centreline
                #   fade=0 (near ego): left = left_wall  (full width)
                #   fade=1 (far):      left = centreline  (right half only)
                new_left = w_l_track[i] + (centre_n - w_l_track[i]) * fade
            else:
                # Left boundary: always the left wall
                new_left = w_l_track[i]
                # Right boundary: funnels from right_wall → centreline
                #   fade=0 (near ego): right = right_wall (full width)
                #   fade=1 (far):      right = centreline  (left half only)
                new_right = w_r_track[i] + (centre_n - w_r_track[i]) * fade

            w_left[i]  = min(w_left[i],  new_left)
            w_right[i] = max(w_right[i], new_right)

        # Overlay: opponent exclusion for any nearby car (front or behind)
        for opp in opp_states:
            opp_s_traj, opp_n_traj = self._predict_opp(opp, t_arr, max_v_node)
            for i in range(max_v_node):
                ds_raw = self._signed_gap(opp_s_traj[i], s_arr[i])
                ds_abs = abs(ds_raw)
                if ds_abs >= self.safety_s:
                    continue
                if ds_raw < -self.behind_ignore_s:
                    continue

                ds_from_ego = i * ds_per_node
                funnel_ramp = min(ds_from_ego / 25.0, 1.0)

                fade_opp = self._cosine_fade(ds_abs, self.safety_s)
                fade_opp *= self._startup_ramp(i)
                fade_opp *= funnel_ramp

                if ds_abs < 15.0 and funnel_ramp > 0.3:
                    safety_excl = max(
                        (self.opp_half_w + self.opp_clearance) * fade_opp,
                        self.overtake_excl_min * funnel_ramp)
                    opp_n = opp_n_traj[i]
                    ego_n = ego_state.get('n', 0.0)
                    if ego_n > opp_n:
                        # Ego is to the left of opponent
                        w_right[i] = max(w_right[i], opp_n + safety_excl)
                    else:
                        w_left[i] = min(w_left[i], opp_n - safety_excl)

        return speed_cap, speed_scale

    # ==================================================================
    # FORCE_LEFT / FORCE_RIGHT -- lock to half-track (no obstacle avoidance)
    # ==================================================================
    def _mode_force_side(self, ego_state, opp_states, s_arr, s_wrapped,
                         t_arr, w_left, w_right, w_l_base, w_r_base,
                         max_v_node, N_stages, force_side,
                         follow_opponents=True):
        """Lock ego strictly to one half of the track.

        Near-end (first N_RAMP nodes): smooth transition from current ego
        position to half-track, ensuring OCP feasibility when ego starts
        on the "wrong" side.  Beyond that: strict half-track lock.

          force_side='right': left=centreline, right=right_wall
          force_side='left':  left=left_wall,  right=centreline

        No opponent exclusion. Speed capped at 22 m/s (race rule).
        C++ PI handles front-car gap control.
        """
        speed_cap = 22.0   # 比赛规则：锁定侧最大 22 m/s
        speed_scale = 1.0

        N_RAMP = 5          # 过渡节点数（约 15-25 m，取决于节点间距）
        EGO_MARGIN = 1.5    # 近端额外保证 ego 可达的裕度 (m)

        rl_len = self.track_handler.raceline_track_length
        s_wrapped_rl = s_arr % rl_len

        # Track boundaries at each node
        w_l_track = np.interp(s_wrapped_rl,
                              self.track_handler.raceline_s,
                              self.track_handler.rl_w_tr_left,
                              period=rl_len) + self.w_l_offset
        w_r_track = np.interp(s_wrapped_rl,
                              self.track_handler.raceline_s,
                              self.track_handler.rl_w_tr_right,
                              period=rl_len) + self.w_r_offset

        # Centreline n coordinate (typically ≈ 0)
        rl_n = np.interp(s_wrapped_rl,
                         self.track_handler.raceline_s,
                         self.track_handler.raceline_n,
                         period=rl_len)

        ego_n = ego_state.get('n', 0.0)

        for i in range(N_stages):
            centre_n = float(rl_n[i])

            # ---- 目标半赛道边界 ----
            if force_side == 'right':
                tgt_left  = centre_n
                tgt_right = w_r_track[i]
            else:
                tgt_left  = w_l_track[i]
                tgt_right = centre_n

            if i < N_RAMP:
                # 线性过渡 alpha: 0 → 1
                alpha = i / N_RAMP
                # 近端 "宽" 边界：保证能包住 ego 当前 n
                wide_left  = min(w_l_track[i], ego_n + EGO_MARGIN)
                wide_right = max(w_r_track[i], ego_n - EGO_MARGIN)
                # 插值
                w_left[i]  = min(w_left[i],  wide_left  * (1 - alpha) + tgt_left  * alpha)
                w_right[i] = max(w_right[i], wide_right * (1 - alpha) + tgt_right * alpha)
            else:
                w_left[i]  = min(w_left[i],  tgt_left)
                w_right[i] = max(w_right[i], tgt_right)

        return speed_cap, speed_scale

    # ==================================================================
    # Heuristic side decision
    # ==================================================================
    def _decide_shadow_side(self, ego_state, opp_states):
        """Auto-select shadow side with heading-aware space calculation."""
        target = self._find_target(ego_state, opp_states)
        if target is None:
            return self._shadow_side or 'left'

        opp_n = target.get('n', 0.0)
        opp_chi = target.get('chi', 0.0)
        proj_half_n, _ = self._heading_aware_projection(opp_chi)
        s_at = target['s'] % self.track_len

        w_l = float(np.interp(s_at, self.track_handler.s,
                               self.track_handler.w_tr_left,
                               period=self.track_len))
        w_r = float(np.interp(s_at, self.track_handler.s,
                               self.track_handler.w_tr_right,
                               period=self.track_len))

        space_l = w_l - (opp_n + proj_half_n)
        space_r = (opp_n - proj_half_n) - w_r

        # Curvature over 80m window
        s_look = np.linspace(s_at, s_at + 80.0, 15) % self.track_len
        omega_vals = np.interp(s_look, self.track_handler.s,
                               self.track_handler.Omega_z,
                               period=self.track_len)
        avg_curv = float(np.mean(omega_vals))
        max_abs_curv = float(np.max(np.abs(omega_vals)))

        # High curvature: FORCE inner side
        if max_abs_curv > 0.03:
            if avg_curv > 0.005:
                return 'right'   # Left turn -> inner = right
            elif avg_curv < -0.005:
                return 'left'    # Right turn -> inner = left

        # Normal: wider side + inner preference
        if avg_curv > 0.005:
            space_r += 2.5
        elif avg_curv < -0.005:
            space_l += 2.5

        # Persistence bonus
        if self._shadow_side is not None:
            if self._shadow_side == 'left':
                space_l += 0.5
            else:
                space_r += 0.5

        return 'left' if space_l >= space_r else 'right'

    def _decide_overtake_side(self, ego_state, opp_states):
        """v9: Overtake direction -- re-evaluate for high curvature."""
        target = self._find_target(ego_state, opp_states)
        if target is not None:
            s_at = target['s'] % self.track_len
            s_look = np.linspace(s_at, s_at + 80.0, 15) % self.track_len
            omega_vals = np.interp(s_look, self.track_handler.s,
                                   self.track_handler.Omega_z,
                                   period=self.track_len)
            max_abs_curv = float(np.max(np.abs(omega_vals)))
            avg_curv = float(np.mean(omega_vals))
            if max_abs_curv > 0.03:
                if avg_curv > 0.005:
                    return 'right'
                elif avg_curv < -0.005:
                    return 'left'
        if self._shadow_side is not None:
            return self._shadow_side
        return self._decide_shadow_side(ego_state, opp_states)

    def overtake_abort_side(self, ego_state, opp_states):
        """When overtake fails, pick shadow side from ego's current position."""
        target = self._find_target(ego_state, opp_states)
        if target is None:
            return self._overtake_side or self._shadow_side or 'left'
        ego_n = ego_state.get('n', 0.0)
        opp_n = target.get('n', 0.0)
        return 'left' if ego_n >= opp_n else 'right'

    # ==================================================================
    # v1 side selection (for multi-car overtake)
    # ==================================================================
    def _choose_side(self, opp_idx, opp_n, w_l, w_r, gap, s_at, opp_chi=0.0):
        proj_half_n, _ = self._heading_aware_projection(opp_chi)
        space_l = w_l - (opp_n + proj_half_n)
        space_r = (opp_n - proj_half_n) - w_r
        s_look = np.linspace(s_at, s_at + 80.0, 15) % self.track_len
        omega_vals = np.interp(s_look, self.track_handler.s,
                               self.track_handler.Omega_z,
                               period=self.track_len)
        avg_curv = float(np.mean(omega_vals))
        max_abs_curv = float(np.max(np.abs(omega_vals)))

        if max_abs_curv > 0.03:
            if avg_curv > 0.005:
                return 'right'
            elif avg_curv < -0.005:
                return 'left'

        if avg_curv > 0.005:
            space_r += 2.5
        elif avg_curv < -0.005:
            space_l += 2.5
        natural_side = 'left' if space_l >= space_r else 'right'
        if gap < self.latch_dist and opp_idx in self._prev_side:
            return self._prev_side[opp_idx]
        return natural_side

    # ==================================================================
    # Overtake window
    # ==================================================================
    def _check_overtake_window(self, ego_state, target, shadow_side):
        """v11: More lenient overtake window check.
        - Wider gap range (0..shadow_ot_gap_thr=25m)
        - Lower space requirement (1.5m)
        - Relaxed speed requirement (dV > -30 km/h)
        - Force-ready when gap < 8m (too close, must act)
        """
        if target is None:
            return False
        gap = self._signed_gap(target['s'], ego_state['s'])
        if gap <= 0 or gap > self.shadow_ot_gap_thr:
            return False

        # v11: 当 gap 很小时 (< 8m)，强制允许超车 (否则会撞上)
        if gap < 8.0:
            return True

        opp_n = target['n']
        opp_chi = target.get('chi', 0.0)
        proj_half_n, _ = self._heading_aware_projection(opp_chi)
        s_w = ego_state['s'] % self.track_len
        w_l_at = float(np.interp(s_w, self.track_handler.s,
                                  self.track_handler.w_tr_left,
                                  period=self.track_len))
        w_r_at = float(np.interp(s_w, self.track_handler.s,
                                  self.track_handler.w_tr_right,
                                  period=self.track_len))
        if shadow_side == 'left':
            space = w_l_at - (opp_n + proj_half_n)
        else:
            space = (opp_n - proj_half_n) - w_r_at
        if space < self.shadow_ot_space:
            return False
        dV = ego_state['V'] - target.get('V', 30.0)
        if dV < -30.0:     # v11: relaxed from -20 to -30
            return False
        return True

    # ==================================================================
    # Utility
    # ==================================================================
    def _find_target(self, ego_state, opp_states, target_id=None):
        best, best_gap = None, 999.0
        for opp in opp_states:
            if target_id is not None and opp.get('id', -1) != target_id:
                continue
            gap = self._signed_gap(opp['s'], ego_state['s'])
            if 0 < gap < best_gap:
                best_gap = gap
                best = opp
        return best

    def _signed_gap(self, s_front, s_rear):
        gap = s_front - s_rear
        if gap > self.track_len / 2:
            gap -= self.track_len
        elif gap < -self.track_len / 2:
            gap += self.track_len
        return gap

    def _predict_opp(self, opp, t_arr, max_v_node):
        leader_V = opp.get('V', 30.0)
        if 'pred_s' in opp and len(opp['pred_s']) >= 2:
            t_opp = np.linspace(0.0, self.cfg.planning_horizon,
                                len(opp['pred_s']))
            opp_s = np.interp(t_arr[:max_v_node], t_opp, opp['pred_s'])
            opp_n = np.interp(t_arr[:max_v_node], t_opp, opp['pred_n'])
        else:
            opp_s = np.array([(opp['s'] + leader_V * t_arr[i])
                              % self.track_len
                              for i in range(max_v_node)])
            opp_n = np.full(max_v_node, opp.get('n', 0.0))
        return opp_s, opp_n

    def _smooth_boundaries(self, w_left, w_right, N_stages):
        """v9: Larger spatial kernel for smoother corridor."""
        k = self.smooth_kernel_size
        if k > 1 and N_stages > k:
            pad_l = np.pad(w_left, (k // 2, k // 2), mode='edge')
            pad_r = np.pad(w_right, (k // 2, k // 2), mode='edge')
            kernel = np.ones(k) / k
            w_l_sm = np.convolve(pad_l, kernel, mode='valid')
            w_r_sm = np.convolve(pad_r, kernel, mode='valid')
            n = min(N_stages, len(w_l_sm))
            w_left[:n] = w_l_sm[:n]
            w_right[:n] = w_r_sm[:n]
        return w_left, w_right

    def _temporal_smooth(self, w_left, w_right, N_stages, mode=None):
        """v9: Temporal EMA - prevent corridor jumps between steps.
        v12: DEFEND / FORCE_SIDE uses higher alpha (0.45) for faster convergence.
        v16: SHADOW uses 0.35 (回退到v14值, SHADOW窗口极短不需要特别温和)."""
        alpha = self._ema_alpha
        if mode in (CarverMode.DEFEND, CarverMode.FORCE_LEFT, CarverMode.FORCE_RIGHT):
            alpha = 0.45  # faster convergence for side-lock modes
        elif mode == CarverMode.SHADOW:
            alpha = 0.35  # v16: 回退到v14值
        if self._prev_w_left is not None and len(self._prev_w_left) == N_stages:
            w_left = alpha * w_left + (1.0 - alpha) * self._prev_w_left
            w_right = alpha * w_right + (1.0 - alpha) * self._prev_w_right
        self._prev_w_left = w_left.copy()
        self._prev_w_right = w_right.copy()
        return w_left, w_right

    def _ensure_feasibility(self, w_left, w_right, w_l_base, w_r_base,
                            N_stages):
        for i in range(N_stages):
            w_left[i] = min(w_left[i], w_l_base[i])
            w_right[i] = max(w_right[i], w_r_base[i])
            width = w_left[i] - w_right[i]
            if width < self.min_corridor:
                c = (w_left[i] + w_right[i]) / 2.0
                w_left[i] = c + self.min_corridor / 2.0
                w_right[i] = c - self.min_corridor / 2.0
        return w_left, w_right

    def _ensure_ego_reachable(self, ego_state, w_left, w_right,
                               w_l_base, w_r_base, N_stages):
        """v9: ALWAYS ensure ego is inside corridor for first n_fix nodes."""
        ego_n = ego_state.get('n', 0.0)
        margin = 1.0
        n_fix = min(10, N_stages)

        for i in range(n_fix):
            alpha = 1.0 - (i / max(n_fix - 1, 1)) ** 2

            needed_left = ego_n + margin
            needed_right = ego_n - margin

            if needed_left > w_left[i]:
                w_left[i] = w_left[i] + alpha * (needed_left - w_left[i])
            if needed_right < w_right[i]:
                w_right[i] = w_right[i] + alpha * (needed_right - w_right[i])

            w_left[i] = min(w_left[i], w_l_base[i])
            w_right[i] = max(w_right[i], w_r_base[i])

            width = w_left[i] - w_right[i]
            if width < self.min_corridor:
                c = (w_left[i] + w_right[i]) / 2.0
                w_left[i] = c + self.min_corridor / 2.0
                w_right[i] = c - self.min_corridor / 2.0

        return w_left, w_right
