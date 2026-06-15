# -*- coding: utf-8 -*-
"""
Heuristic tactical policy v12 -- Racing policy with DEFEND mode.

Design (v12):
  1. gap > 20m: RACELINE, full speed chase
  2. gap <= 20m: SHADOW with funnel corridor
  3. OVERTAKE: wide corridor, full speed
  4. Failed overtake: HOLD with tight gap, quick retry
  5. HOLD timeout -> SHADOW -> retry
  6. DEFEND: when rear car within 20m AND no active attack,
     yield to outer side of next turn, let pursuer pass on inner.
     Decoupled from attack FSM via attack_immunity timer.

Phase flow:
  RACELINE (gap>20) -> SHADOW (gap<=20, funnel corridor)
  -> OVERTAKE (gap<=18, ready) -> (success) RACELINE
                                -> (fail) HOLD -> SHADOW -> retry

  RACELINE (rear car < 20m, no attack) -> DEFEND (yield outer side)
  -> RACELINE (rear car passed & > 20m ahead)
"""

import numpy as np
from typing import Optional, List

from tactical_decision.tactical_action import (
    TacticalAction, DiscreteTactic, PreferenceVector,
)
from tactical_decision.observation import TacticalObservation, OpponentState
from tactical_decision.config import TacticalConfig, DEFAULT_CONFIG


class HeuristicTacticalPolicy:
    """Stateful heuristic tactical policy v9."""

    def __init__(self, cfg: TacticalConfig = DEFAULT_CONFIG,
                 force_side: str = None,
                 follow_when_forced: bool = True):
        """
        Parameters
        ----------
        cfg : TacticalConfig
        force_side : None | 'left' | 'right'
            When set, the ego will hug the specified track boundary
            instead of running the normal FSM logic.  The transition
            from the current position is handled smoothly by the carver.
        follow_when_forced : bool
            Only used when ``force_side`` is set.
            True  -> slow down and avoid opponents (follow behaviour).
            False -> completely ignore opponents (pure side-hug).
        """
        self.cfg = cfg
        self.dt = float(cfg.assumed_calc_time)

        # ---- Force-side override (does NOT disturb normal FSM) ----
        self._force_side: str = force_side        # None | 'left' | 'right'
        self._follow_when_forced: bool = follow_when_forced

        # ---- FSM state ----
        self.phase: str = "RACELINE"
        self.target_id: Optional[int] = None
        self.phase_time: float = 0.0

        # Overtake lock
        self._overtake_locked: bool = False
        self._abort_cooldown: int = 0

        # Hold mode
        self._hold_steps: int = 0
        self._hold_side: Optional[str] = None

        # Shadow/Overtake side
        self.locked_side: Optional[str] = None

        # External signal from carver
        self._overtake_ready_ext: bool = False

        # ---- Thresholds (v16 race-exam) ----
        # 策略: RACELINE 全速追 → SHADOW 极短引导方向 → OVERTAKE → 失败 HOLD → 重试
        # v16: 回归经典"重RACE轻SHADOW"，SHADOW窗口仅2m(20→18)，几乎不减速
        # v20: 全部改为读 cfg，便于在线调参 / optimize 搜索
        self.chase_gap = float(cfg.chase_gap)
        self.shadow_gap = float(cfg.chase_gap)        # 与 chase_gap 一致 (legacy)
        self.ot_gap = float(cfg.ot_gap)
        self.abort_gap = float(cfg.abort_gap)
        self.hold_duration = int(cfg.hold_duration_steps)
        self.hold_entry_gap = float(cfg.hold_entry_gap)
        self.hold_exit_gap = float(cfg.hold_exit_gap)
        self.t_react = float(cfg.t_react)
        self.t_overtake = float(cfg.t_overtake)
        self.curv_straight = float(cfg.curv_straight)
        self.ego_ahead_margin = cfg.vehicle_length

        # ---- DEFEND mode thresholds (v12) ----
        self.defend_rear_detect  = 20.0   # 后方 20m 内有车触发防守
        self.defend_front_clear  = 25.0   # 前方 25m 内无车才允许防守 (避免正在追车时切防守)
        self.defend_clear_zone   = 50.0   # 退出条件：前后 30m 内都无对手才退出
        self.defend_min_duration = 30     # 最小停留 30 步 (~3.75s)，进入后必须维持
        self.attack_immunity_max = int(cfg.attack_immunity_steps)
        self._attack_immunity: int = 0    # countdown timer
        self._defend_steps: int = 0       # DEFEND 已停留步数（进入时置零）
        self._defend_side: Optional[str] = None   # 防守让路方向 (弯道外侧)
        self._defend_target_id: Optional[int] = None  # 被防守的后方车 ID

        # ---- P2P request output (NEW) ----
        # 由 tactical_node 通过 guidance 转发给 planner; planner 自己执行 2/lap+15s 限制
        self._p2p_request: bool = False
        self._p2p_request_reason: str = ""

        # ---- Carver mode output ----
        self._carver_mode_str = 'raceline'
        self._carver_side = None

        # ---- CH8: static obstacle early-overtake mode ----
        self._ch8_mode: bool = False

        # ---- Debug ----
        self.debug_info = {}

    # ------------------------------------------------------------------
    # Force-side runtime control
    # ------------------------------------------------------------------
    @property
    def force_side(self) -> Optional[str]:
        return self._force_side

    @force_side.setter
    def force_side(self, value: Optional[str]):
        """Set to 'left', 'right', or None (disable) at runtime."""
        assert value in (None, 'left', 'right'), f"Invalid force_side: {value}"
        self._force_side = value

    @property
    def follow_when_forced(self) -> bool:
        return self._follow_when_forced

    @follow_when_forced.setter
    def follow_when_forced(self, value: bool):
        self._follow_when_forced = bool(value)

    # ------------------------------------------------------------------
    @property
    def carver_mode_str(self) -> str:
        return self._carver_mode_str

    @property
    def carver_side(self) -> Optional[str]:
        return self._carver_side

    def set_overtake_ready(self, ready: bool):
        self._overtake_ready_ext = ready

    def set_ch8_mode(self, enabled: bool):
        """Enable/disable CH8 static obstacle early-overtake mode.
        When enabled, act() bypasses all FSM logic entirely."""
        self._ch8_mode = bool(enabled)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def act(self, obs: TacticalObservation) -> TacticalAction:
        self.phase_time += self.dt

        if self._abort_cooldown > 0:
            self._abort_cooldown -= 1
        if self._hold_steps > 0:
            self._hold_steps -= 1
        if self._attack_immunity > 0:
            self._attack_immunity -= 1

        # ============================================================
        # CH8 static obstacle mode: bypass ALL FSM logic
        # Just output ch8_static carver mode + pick overtake side
        # ============================================================
        if self._ch8_mode:
            target, all_opp = self._select_target(obs)
            gap = abs(target.delta_s) if target is not None else 999.0
            # CH8: 每帧按对手实际位置重新选边（空间更大的一侧）
            # 不锁定历史 side，因为 carver v2 自己按 opp_n 决定方向
            if target is not None:
                # delta_n = ego_n - opp_n, opp 在左(opp_n>ego_n) → delta_n<0
                # 对手偏左 → 右侧空间更大 → side='right'
                # 对手偏右 → 左侧空间更大 → side='left'
                opp_n_approx = obs.ego_n - target.delta_n
                if opp_n_approx > 0:
                    self.locked_side = 'right'
                else:
                    self.locked_side = 'left'
            self._set_phase("CH8_STATIC")
            self._carver_mode_str = 'ch8_static'
            self._carver_side = self.locked_side
            self._build_debug(obs, target, gap)
            return self._make_raceline_action(obs)

        # ---- Target: nearest opponent AHEAD ----
        target, all_opp = self._select_target(obs)

        # ============================================================
        # v12-fix: DEFEND priority gate
        # 当前处于 DEFEND 时，必须在这里先检查维持/退出条件。
        # 只有当 _check_defend 返回 None (该退出了) 时才继续正常 FSM。
        # 这样防止对手超过 ego 后、变成"前方对手"时被 gap 逻辑
        # 误判为 SHADOW/OVERTAKE，从而绕过 DEFEND 的最小停留和清场检查。
        # ============================================================
        if self.phase == "DEFEND":
            defend_result = self._check_defend(obs, front_gap=999.0)
            if defend_result is not None:
                return defend_result
            # _check_defend returned None → DEFEND exit confirmed
            # 强制切回 RACELINE 并返回，本帧不再执行其他 FSM 逻辑
            # 避免退出 DEFEND 后被 gap 判断立刻拉进 SHADOW/OVERTAKE
            self._reset_to_raceline()
            return self._finalize(obs, target, None,
                                  self._make_raceline_action(obs))

        if target is None:
            # No opponent ahead -- check DEFEND (rear car approaching?)
            defend_result = self._check_defend(obs, front_gap=999.0)
            if defend_result is not None:
                return defend_result
            self._reset_to_raceline()
            return self._finalize(obs, target, None,
                                  self._make_raceline_action(obs))

        gap = abs(target.delta_s)
        ego_is_ahead = (target.delta_s > self.ego_ahead_margin)

        # ============================================================
        # Ego ahead -> switch target or RACELINE / DEFEND
        # ============================================================
        if ego_is_ahead:
            if self._overtake_locked:
                self._overtake_locked = False
                self._hold_steps = 0
                self._hold_side = None
                # v12: 超车刚结束，设置攻击免疫
                self._attack_immunity = self.attack_immunity_max

            next_t = self._find_next_target(obs,
                                            exclude_id=target.vehicle_id)
            if next_t is not None:
                self.target_id = next_t.vehicle_id
                target = next_t
                gap = abs(target.delta_s)
                ego_is_ahead = (target.delta_s > self.ego_ahead_margin)
                self.locked_side = None
                if ego_is_ahead:
                    # Check DEFEND before going to RACELINE
                    defend_result = self._check_defend(obs, front_gap=gap)
                    if defend_result is not None:
                        return defend_result
                    self._reset_to_raceline()
                    return self._finalize(obs, target, gap,
                                          self._make_raceline_action(obs))
            else:
                # No front target at all — check DEFEND
                defend_result = self._check_defend(obs, front_gap=999.0)
                if defend_result is not None:
                    return defend_result
                self._reset_to_raceline()
                return self._finalize(obs, target, gap,
                                      self._make_raceline_action(obs))

        # ============================================================
        # Closing-speed adaptive thresholds
        # delta_V > 0 means ego is closing on opponent (Frenet s-direction)
        # ============================================================
        closing_speed = max(target.delta_V, 0.0)

        # ---- 保守兜底：opponent V 估算还没收敛（首帧 / leader 切换） ----
        # 仅在 gap 很近 且 closing≈0 时启用，帮助 RACELINE→SHADOW 提前过渡
        ego_V = float(getattr(obs, 'ego_V', 30.0))
        if closing_speed < 1.0 and gap < 25.0 and ego_V > 5.0:
            closing_speed = max(closing_speed, ego_V * 0.5)

        T_react = self.t_react
        T_overtake = self.t_overtake
        dyn_chase_gap = float(np.clip(
            max(self.chase_gap, closing_speed * T_react), self.chase_gap, 80.0))
        dyn_ot_gap = float(np.clip(
            max(self.ot_gap, closing_speed * T_overtake), self.ot_gap, 60.0))
        # abort_gap: 不随 closing_speed 膨胀 — 避免高逼近速度时过早 abort 超车
        # 2026-04-30 v4: 直接使用 self.abort_gap (接通 RL a[6])；
        # 原公式 chase_gap+5 被 hard-clip 已保证 abort >= chase+5
        dyn_abort_gap = float(self.abort_gap)

        # ============================================================
        # Overtake locked -> check abort / continue
        # ============================================================
        if self._overtake_locked:
            lat_clear = abs(target.delta_n)
            being_dropped = (target.delta_V <= 0.5)
            lat_abort = (lat_clear < 2.0 and gap < 6.0 and being_dropped)

            # v18: 远距离 abort 不进 HOLD，直接退到 SHADOW 重试
            HOLD_ENTRY_GAP = self.hold_entry_gap
            if gap > dyn_abort_gap or lat_abort:
                self._overtake_locked = False
                self._abort_cooldown = 8
                self._attack_immunity = self.attack_immunity_max
                if gap <= HOLD_ENTRY_GAP:
                    # 贴近 abort → 进 HOLD 咬住前车
                    self._hold_side = self.locked_side
                    self._hold_steps = self.hold_duration
                    self._set_phase("HOLD")
                else:
                    # 距离已拉开 → 跳过 HOLD，直接 SHADOW 准备重试
                    self._hold_steps = 0
                    self._hold_side = None
                    self._set_phase("SHADOW")
                    return self._finalize(obs, target, gap,
                                          self._make_shadow_action(obs, target))
            else:
                self._set_phase("OVERTAKE")
                return self._finalize(obs, target, gap,
                                      self._make_overtake_action(obs, target))

        # ============================================================
        # HOLD mode -- 紧咬前车, 等待重试超车
        # 退出: ① gap 拉太远 → 没意义, 退 SHADOW; ② OT 时机 → OVERTAKE; ③ 倒计时
        # ============================================================
        if self._hold_steps > 0:
            self._set_phase("HOLD")

            # v18: 主动退出 — gap 已拉到 > 25m 说明速度策略没咬住, 没必要继续 HOLD
            HOLD_EXIT_GAP = self.hold_exit_gap
            if gap > HOLD_EXIT_GAP:
                self._hold_steps = 0
                self._hold_side = None
                self._set_phase("SHADOW")
                return self._finalize(obs, target, gap,
                                      self._make_shadow_action(obs, target))

            if (gap < dyn_ot_gap and self._overtake_ready_ext
                    and self._abort_cooldown == 0):
                self.locked_side = self._revalidate_overtake_side(obs, target)
                self._overtake_locked = True
                self._hold_steps = 0
                self._set_phase("OVERTAKE")
                return self._finalize(obs, target, gap,
                                      self._make_overtake_action(obs, target))

            if self._hold_steps == 0:
                self._attack_immunity = self.attack_immunity_max  # v12: HOLD→SHADOW 也免疫
                self._set_phase("SHADOW")
                return self._finalize(obs, target, gap,
                                      self._make_shadow_action(obs, target))

            return self._finalize(obs, target, gap,
                                  self._make_hold_action(obs, target))

        # ============================================================
        # Normal mode selection (RACELINE → SHADOW → OVERTAKE)
        # Closing-speed adaptive: dynamic thresholds
        # ============================================================
        if gap > dyn_chase_gap:
            # 前方对手较远 — 检查 DEFEND (后方是否有车逼近)
            defend_result = self._check_defend(obs, front_gap=gap)
            if defend_result is not None:
                return defend_result

            self._set_phase("RACELINE")
            self.locked_side = None
            return self._finalize(obs, target, gap,
                                  self._make_raceline_action(obs))

        # gap <= chase_gap: 进入 SHADOW 跟踪预备 (不检查 DEFEND)
        # v14: SHADOW 侧锁定 — 进入 SHADOW 时选一次侧，整个周期不再变
        #      只有退回 RACELINE 时才清除 locked_side
        if self.locked_side is None:
            self.locked_side = self._choose_side(obs, target)

        is_inner_side = self._is_inner_side(obs, target)
        straight_enough = (obs.upcoming_max_curvature < self.curv_straight)
        allow_ot = straight_enough or is_inner_side

        if (gap <= dyn_ot_gap and self._overtake_ready_ext
                and self._abort_cooldown == 0
                and allow_ot):
            self.locked_side = self._revalidate_overtake_side(obs, target)
            self._overtake_locked = True
            self._set_phase("OVERTAKE")
            return self._finalize(obs, target, gap,
                                  self._make_overtake_action(obs, target))

        # v14: 删除每 40 步重选侧的逻辑 — SHADOW 期间 locked_side 绝不变

        self._set_phase("SHADOW")
        return self._finalize(obs, target, gap,
                              self._make_shadow_action(obs, target))

    # ------------------------------------------------------------------
    # DEFEND logic (v12)
    # ------------------------------------------------------------------
    def _check_defend(self, obs: TacticalObservation,
                      front_gap: float) -> Optional[TacticalAction]:
        """Check if DEFEND should be active. Returns action if yes, None if no.

        DEFEND triggers when ALL conditions are met:
          1. Currently in RACELINE or DEFEND (not in SHADOW/OVERTAKE/HOLD)
          2. attack_immunity == 0 (no recent overtake activity)
          3. front_gap > defend_front_clear (not actively chasing)
          4. A rear opponent is within defend_rear_detect (20m)

        DEFEND exits when ALL are met:
          - Minimum stay time elapsed (defend_min_duration steps)
          - No opponent within ±defend_clear_zone (15m) in front OR behind
        """
        # Gate 1: only from RACELINE or already DEFEND
        if self.phase not in ("RACELINE", "DEFEND"):
            return None

        # Gate 2: attack immunity
        if self._attack_immunity > 0:
            if self.phase == "DEFEND":
                # Immunity activated while in DEFEND (e.g. params changed)
                # → force exit
                self._defend_side = None
                self._defend_target_id = None
                self._defend_steps = 0
            return None

        # Currently in DEFEND — check exit
        if self.phase == "DEFEND":
            self._defend_steps += 1

            # Minimum stay: must remain in DEFEND for at least N steps
            if self._defend_steps < self.defend_min_duration:
                # Not yet, stay in DEFEND unconditionally
                self._set_phase("DEFEND")
                nearest_gap = self._nearest_opponent_distance(obs)
                return self._finalize(obs, None, nearest_gap,
                                      self._make_defend_action(obs))

            # Minimum time elapsed — now check exit condition:
            # Front AND rear clear_zone (15m) must be free of opponents
            if self._is_zone_clear(obs, self.defend_clear_zone):
                # All clear — safe to exit DEFEND
                self._defend_side = None
                self._defend_target_id = None
                self._defend_steps = 0
                return None  # fall through to RACELINE

            # Zone not clear — stay in DEFEND
            self._set_phase("DEFEND")
            nearest_gap = self._nearest_opponent_distance(obs)
            return self._finalize(obs, None, nearest_gap,
                                  self._make_defend_action(obs))

        # ============================================================
        # Currently in RACELINE — check entry into DEFEND
        # ============================================================
        # Gate 3: not actively chasing a front car
        if front_gap < self.defend_front_clear:
            return None

        # Find nearest rear opponent
        rear_opp = self._find_rear_opponent(obs)
        if rear_opp is None:
            return None

        rear_gap = rear_opp.delta_s  # positive = ego ahead of rear car
        if rear_gap < 0 or rear_gap > self.defend_rear_detect:
            return None

        # ---- Enter DEFEND ----
        # v12: 固定往右侧收敛，不判断弯道方向
        self._defend_side = 'right'

        self._defend_target_id = rear_opp.vehicle_id
        self._defend_steps = 0  # reset counter on entry
        self._set_phase("DEFEND")
        return self._finalize(obs, None, rear_gap,
                              self._make_defend_action(obs))

    def _is_zone_clear(self, obs: TacticalObservation, zone: float) -> bool:
        """Check that no opponent is within ±zone metres (front or behind)."""
        for opp in obs.opponents:
            if abs(opp.delta_s) < zone:
                return False
        return True

    def _nearest_opponent_distance(self, obs: TacticalObservation) -> float:
        """Return abs distance to nearest opponent (for debug display)."""
        if not obs.opponents:
            return 999.0
        return min(abs(o.delta_s) for o in obs.opponents)

    def _find_rear_opponent(self, obs: TacticalObservation) -> Optional[OpponentState]:
        """Find the closest opponent BEHIND ego (delta_s > 0, within 20m)."""
        rear = [o for o in obs.opponents
                if o.delta_s > 0 and o.delta_s < self.defend_rear_detect]
        if not rear:
            return None
        rear.sort(key=lambda o: o.delta_s)  # closest behind first
        return rear[0]

    # ------------------------------------------------------------------
    def _finalize(self, obs, target, gap, action):
        self._update_carver_output()
        self._evaluate_p2p(obs, target, gap)
        self._build_debug(obs, target, gap)
        return action

    # ------------------------------------------------------------------
    # P2P request evaluation (NEW)
    # planner 端最终执行 2/lap+15s+冷却限制；这里只发"建议请求"。
    # 触发条件 (全部满足):
    #   - phase ∈ {OVERTAKE, SHADOW, HOLD}
    #   - target 存在 且 gap ∈ [min_gap, max_gap]
    #   - closing speed > min_closing (正在咬车 / 不被甩开)
    #   - ego_V ≥ min_speed (直道才有意义)
    #   - upcoming_max_curvature ≤ max_curvature (前方直)
    # ------------------------------------------------------------------
    def _evaluate_p2p(self, obs, target, gap):
        if not getattr(self.cfg, 'p2p_tactical_enable', True):
            self._p2p_request = False
            return
        if target is None or gap is None or gap < 0:
            self._p2p_request = False
            return
        if self.phase not in ("OVERTAKE", "SHADOW", "HOLD"):
            self._p2p_request = False
            return
        gmin = float(getattr(self.cfg, 'p2p_tactical_min_gap', 8.0))
        gmax = float(getattr(self.cfg, 'p2p_tactical_max_gap', 30.0))
        if not (gmin <= gap <= gmax):
            self._p2p_request = False
            return
        if float(getattr(target, 'delta_V', 0.0)) < float(
                getattr(self.cfg, 'p2p_tactical_min_closing', -2.0)):
            self._p2p_request = False
            return
        ego_V = float(getattr(obs, 'ego_V', 0.0))
        if ego_V < float(getattr(self.cfg, 'p2p_tactical_min_speed', 50.0)):
            self._p2p_request = False
            return
        kmax = float(getattr(self.cfg, 'p2p_tactical_max_curvature', 0.005))
        if float(getattr(obs, 'upcoming_max_curvature', 0.0)) > kmax:
            self._p2p_request = False
            return
        self._p2p_request = True
        self._p2p_request_reason = (
            f"phase={self.phase} gap={gap:.1f} dV={target.delta_V:.1f} "
            f"V={ego_V:.1f}")

    @property
    def p2p_request(self) -> bool:
        return bool(self._p2p_request)

    # ------------------------------------------------------------------
    # Carver mode mapping
    # ------------------------------------------------------------------
    def _update_carver_output(self):
        # Force-side override takes priority but does NOT touch FSM state
        if self._force_side is not None:
            if self._force_side == 'left':
                self._carver_mode_str = 'force_left'
            else:
                self._carver_mode_str = 'force_right'
            self._carver_side = self._force_side
            return

        if self.phase == "RACELINE":
            self._carver_mode_str = 'raceline'
            self._carver_side = None
        elif self.phase == "SHADOW":
            self._carver_mode_str = 'shadow'
            self._carver_side = self.locked_side
        elif self.phase == "OVERTAKE":
            self._carver_mode_str = 'overtake'
            self._carver_side = self.locked_side
        elif self.phase == "HOLD":
            self._carver_mode_str = 'hold'
            self._carver_side = self._hold_side
        elif self.phase == "DEFEND":
            self._carver_mode_str = 'defend'
            self._carver_side = self._defend_side
        else:
            self._carver_mode_str = 'raceline'
            self._carver_side = None

    # ------------------------------------------------------------------
    def _set_phase(self, phase: str):
        if phase != self.phase:
            self.phase = phase
            self.phase_time = 0.0

    def _reset_to_raceline(self):
        self.phase = "RACELINE"
        self.phase_time = 0.0
        self._overtake_locked = False
        self._hold_steps = 0
        self._hold_side = None
        self._abort_cooldown = 0

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------
    def _select_target(self, obs: TacticalObservation):
        ahead = [o for o in obs.opponents
                 if o.delta_s < 0 and abs(o.delta_s) < 120.0]
        alongside = [o for o in obs.opponents
                     if abs(o.delta_s) <= self.ego_ahead_margin
                     and o not in ahead]
        all_relevant = ahead + alongside

        if not all_relevant:
            just_behind = [o for o in obs.opponents
                           if o.delta_s > 0 and o.delta_s < 10.0]
            if just_behind:
                all_relevant = just_behind

        if not all_relevant:
            return None, []

        all_relevant.sort(key=lambda o: abs(o.delta_s))

        if self.target_id is not None and self._overtake_locked:
            for o in all_relevant:
                if o.vehicle_id == self.target_id:
                    return o, all_relevant

        target = all_relevant[0]
        self.target_id = target.vehicle_id
        return target, all_relevant

    def _find_next_target(self, obs: TacticalObservation,
                          exclude_id: int) -> Optional[OpponentState]:
        ahead = [o for o in obs.opponents
                 if o.delta_s < -self.ego_ahead_margin
                 and o.vehicle_id != exclude_id
                 and abs(o.delta_s) < 120.0]
        if not ahead:
            return None
        ahead.sort(key=lambda o: abs(o.delta_s))
        return ahead[0]

    # ------------------------------------------------------------------
    # Side selection — cost-function + hysteresis
    # ------------------------------------------------------------------
    def _choose_side(self, obs: TacticalObservation,
                     target: OpponentState) -> str:
        """Select overtake/shadow side using a weighted cost function.

        Factors considered:
          1. Available space: more room on one side → prefer it
          2. Curvature: prefer inner side of upcoming turn (shorter path)
          3. Raceline alignment: prefer the side closer to the raceline
          4. Ego momentum: prefer the side ego is already moving toward
          5. Hysteresis: bonus for current side to prevent oscillation

        Returns 'left' or 'right'.
        """
        return self._score_side(obs, target, hysteresis_bonus=1.5)

    def _revalidate_overtake_side(self, obs: TacticalObservation,
                                   target: OpponentState) -> str:
        """Re-evaluate side at overtake entry/retry with stronger hysteresis."""
        return self._score_side(obs, target, hysteresis_bonus=2.5)

    def _score_side(self, obs: TacticalObservation,
                    target: OpponentState,
                    hysteresis_bonus: float = 1.5) -> str:
        """Core scoring function for side selection.

        Computes a score for left and right; higher score wins.
        """
        ego_n = obs.ego_n
        opp_n = ego_n - target.delta_n   # opponent absolute n

        # --- Heading-aware opponent half-width ---
        opp_chi = target.chi
        veh_L = 5.30
        veh_W = 1.93
        abs_sin = abs(np.sin(opp_chi))
        abs_cos = abs(np.cos(opp_chi))
        proj_half_n = max((veh_L * abs_sin + veh_W * abs_cos) / 2.0,
                          veh_W / 2.0)

        # --- Factor 1: Available space (dominant factor) ---
        space_l = float(obs.w_left) - (opp_n + proj_half_n)
        space_r = (opp_n - proj_half_n) - float(obs.w_right)
        min_pass_width = 3.0  # minimum width to consider a side viable
        score_l = max(space_l - min_pass_width, 0.0)
        score_r = max(space_r - min_pass_width, 0.0)

        # --- Factor 2: Curvature — inner side bonus ---
        curv_sign = getattr(obs, 'upcoming_curvature_sign', 0.0)
        curv_mag = abs(curv_sign)
        curv_bonus = min(curv_mag / 0.02, 1.0) * 2.0
        if curv_sign > 0.003:
            score_l += curv_bonus   # left turn → inner = left
        elif curv_sign < -0.003:
            score_r += curv_bonus   # right turn → inner = right

        # --- Factor 3: Ego momentum — prefer side ego is already on ---
        lateral_offset = ego_n - opp_n
        momentum_bonus = min(abs(lateral_offset) / 2.0, 1.0) * 1.0
        if lateral_offset > 0.5:
            score_l += momentum_bonus  # ego is left of opponent
        elif lateral_offset < -0.5:
            score_r += momentum_bonus  # ego is right of opponent

        # --- Factor 4: Hysteresis — bonus for current locked side ---
        if self.locked_side == 'left':
            score_l += hysteresis_bonus
        elif self.locked_side == 'right':
            score_r += hysteresis_bonus

        # --- Viability gate: if one side has no room, force the other ---
        if space_l < min_pass_width and space_r >= min_pass_width:
            return 'right'
        if space_r < min_pass_width and space_l >= min_pass_width:
            return 'left'

        return 'left' if score_l >= score_r else 'right'

    def _is_inner_side(self, obs: TacticalObservation,
                       target: OpponentState) -> bool:
        if self.locked_side is None:
            return False
        curv_sign = getattr(obs, 'upcoming_curvature_sign', 0.0)
        if curv_sign > 0.005 and self.locked_side == 'left':
            return True
        if curv_sign < -0.005 and self.locked_side == 'right':
            return True
        return False

    # ------------------------------------------------------------------
    # Action generation
    # ------------------------------------------------------------------
    def _make_raceline_action(self, obs):
        return TacticalAction(
            discrete_tactic=DiscreteTactic.RACE_LINE,
            aggressiveness=1.0,
            preference=PreferenceVector(
                rho_v=0.0, rho_n=0.0, rho_s=1.0, rho_w=1.0,
            ),
            p2p_trigger=False,
        )

    def _make_shadow_action(self, obs, target):
        side = self.locked_side or "left"
        if side == "left":
            tactic = DiscreteTactic.PREPARE_OVERTAKE_LEFT
            rho_n = 0.4
        else:
            tactic = DiscreteTactic.PREPARE_OVERTAKE_RIGHT
            rho_n = -0.4
        return TacticalAction(
            discrete_tactic=tactic,
            aggressiveness=0.95,
            preference=PreferenceVector(
                rho_v=0.05, rho_n=rho_n, rho_s=1.0, rho_w=1.2,
            ),
            p2p_trigger=False,
        )

    def _make_overtake_action(self, obs, target):
        side = self.locked_side or "left"
        if side == "left":
            tactic = DiscreteTactic.OVERTAKE_LEFT
            rho_n = 1.0
        else:
            tactic = DiscreteTactic.OVERTAKE_RIGHT
            rho_n = -1.0

        gap = abs(target.delta_s)
        dv = float(obs.ego_V - target.V)
        use_p2p = (obs.p2p_available and gap < 12.0
                   and obs.upcoming_max_curvature < 0.015 and dv < 3.0)
        return TacticalAction(
            discrete_tactic=tactic,
            aggressiveness=1.0,
            preference=PreferenceVector(
                rho_v=0.15, rho_n=rho_n, rho_s=1.0, rho_w=1.5,
            ),
            p2p_trigger=use_p2p,
        )

    def _make_hold_action(self, obs, target):
        return TacticalAction(
            discrete_tactic=DiscreteTactic.RACE_LINE,
            aggressiveness=0.9,
            preference=PreferenceVector(
                rho_v=0.05, rho_n=0.0, rho_s=1.0, rho_w=1.0,
            ),
            p2p_trigger=False,
        )

    def _make_defend_action(self, obs):
        """v12: DEFEND — yield to outer side, full speed."""
        side = self._defend_side or 'right'
        if side == 'left':
            tactic = DiscreteTactic.DEFEND_LEFT
            rho_n = 0.6
        else:
            tactic = DiscreteTactic.DEFEND_RIGHT
            rho_n = -0.6
        return TacticalAction(
            discrete_tactic=tactic,
            aggressiveness=0.95,
            preference=PreferenceVector(
                rho_v=0.0, rho_n=rho_n, rho_s=1.0, rho_w=1.0,
            ),
            p2p_trigger=False,
        )

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------
    def _build_debug(self, obs, target, gap):
        closing_speed = max(target.delta_V, 0.0) if target is not None else 0.0
        self.debug_info = {
            "phase": self.phase,
            "target_id": self.target_id,
            "gap": gap,
            "locked_side": self.locked_side,
            "phase_time": self.phase_time,
            "cooldown_time": self._abort_cooldown * self.dt,
            "raw_tactic": "N/A",
            "safe_set": [],
            "carver_mode": self._carver_mode_str,
            "carver_side": self._carver_side,
            "overtake_ready_ext": self._overtake_ready_ext,
            "hold_steps": self._hold_steps,
            "overtake_locked": self._overtake_locked,
            "attack_immunity": self._attack_immunity,
            "defend_side": self._defend_side,
            "defend_target_id": self._defend_target_id,
            "defend_steps": self._defend_steps,
            "closing_speed": closing_speed,
        }

    # ------------------------------------------------------------------
    # Legacy compatibility
    # ------------------------------------------------------------------
    def get_continuous_target(self, discrete_tactic, obs):
        if discrete_tactic == DiscreteTactic.FOLLOW_CENTER:
            return np.array([0.85, 0.08, 0.0, 1.00, 1.15])
        elif discrete_tactic == DiscreteTactic.RACE_LINE:
            return np.array([1.00, 0.00, 0.0, 1.00, 1.00])
        elif discrete_tactic == DiscreteTactic.OVERTAKE_LEFT:
            return np.array([1.00, 0.18, 1.15, 0.90, 1.70])
        elif discrete_tactic == DiscreteTactic.OVERTAKE_RIGHT:
            return np.array([1.00, 0.18, -1.15, 0.90, 1.70])
        elif discrete_tactic == DiscreteTactic.DEFEND_LEFT:
            return np.array([0.70, 0.03, 0.60, 1.10, 1.50])
        elif discrete_tactic == DiscreteTactic.DEFEND_RIGHT:
            return np.array([0.70, 0.03, -0.60, 1.10, 1.50])
        elif discrete_tactic == DiscreteTactic.PREPARE_OVERTAKE_LEFT:
            return np.array([0.92, 0.10, 0.70, 0.95, 1.55])
        elif discrete_tactic == DiscreteTactic.PREPARE_OVERTAKE_RIGHT:
            return np.array([0.92, 0.10, -0.70, 0.95, 1.55])
        else:
            return np.array([0.7, 0.0, 0.0, 1.0, 1.0])
