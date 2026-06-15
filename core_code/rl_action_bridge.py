"""ROS2-side helpers for RL Env: subscribe state/v2v/collision/lap, publish action.

Lives in a single rclpy node with multi-thread executor so the gym Env
can call read_obs() / publish_action() from any thread.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from std_msgs.msg import Float64, Float64MultiArray
from geometry_msgs.msg import Point, PoseStamped

try:
    from autonoma_msgs.msg import GroundTruthArray  # type: ignore
    HAVE_GTA = True
except Exception:
    HAVE_GTA = False


# ---- Action bounds (must match rl_policy.py) ----
# v23 (2026-04-30): widened L/R upper bounds 2.5 -> 6.0, raised lower 0.3 -> 1.5,
#   so RL has the option to NOT shrink the carver corridor (track half-width ~7m).
#   Also tightened safety_margin upper 1.2 -> 0.8 so RL can't blow up opp_clearance.
ACTION_BOUNDS: List[Tuple[float, float]] = [
    (1.5, 6.0),    # 0  corridor_left_margin   (was 0.3-2.5)
    (1.5, 6.0),    # 1  corridor_right_margin  (was 0.3-2.5)
    (0.2, 0.8),    # 2  corridor_safety_margin -> carver.lateral_safety / opp_clearance (was 0.2-1.2)
    (15.0, 90.0),  # 3  follow_speed_cap_mps  (HOLD/FOLLOW desired speed cap, replaces follow_gap)
    (10.0, 35.0),  # 4  chase_gap
    (12.0, 35.0),  # 5  ot_gap
    (20.0, 50.0),  # 6  abort_gap (now read directly by FSM)
    (-1.5, 1.5),   # 7  lateral_bias
    (1.0, 5.0),    # 8  w_safe -> carver.V_max via 80*clip(2/w_safe, 0.4, 1.0)
]
ACTION_DIM = len(ACTION_BOUNDS)


def tanh_to_action(tanh_vec: np.ndarray) -> np.ndarray:
    """Map tanh output [-1, 1]^9 → physical action ranges, with hard safety clip."""
    out = np.empty(ACTION_DIM, dtype=np.float64)
    for i, (lo, hi) in enumerate(ACTION_BOUNDS):
        v = float(tanh_vec[i])
        v = max(-1.0, min(1.0, v))
        out[i] = lo + 0.5 * (v + 1.0) * (hi - lo)

    # ---- Hard safety clip ----
    # chase >= ot - 2
    if out[4] < out[5] - 2:
        out[4] = out[5] - 2
    # abort >= chase + 5
    if out[6] < out[4] + 5:
        out[6] = out[4] + 5
    # L + R >= 0.8
    if out[0] + out[1] < 0.8:
        out[1] = 0.8 - out[0]
    # follow_speed_cap clipped to >= 15 by lower bound

    return out


@dataclass
class LatestObs:
    ego_s: float = 0.0
    ego_n: float = 0.0
    ego_V: float = 0.0
    ego_chi: float = 0.0
    ego_ax: float = 0.0
    ego_ay: float = 0.0
    w_left: float = 7.0
    w_right: float = -7.0
    curvature: float = 0.0
    n_opp: int = 0
    opps: List[Dict] = field(default_factory=list)
    fsm_mode: int = 0
    last_update_t: float = 0.0


class RLBridgeNode(Node):
    """Single ROS2 node owned by the RL env."""

    def __init__(self):
        super().__init__('a2rl_rl_bridge')
        self._lock = threading.RLock()
        self._obs = LatestObs()
        # reward inputs
        self._latest_lap_time: Optional[float] = None
        self._lap_time_consumed = True
        self._latest_lat_pct: float = 0.0
        self._collision_count = 0
        self._collision_seen = 0
        self._collision_wall = 0
        self._collision_opp = 0
        self._v2v_opps: List[Dict] = []  # full from /flyeagle/v2v_ground_truth
        self._ego_pose: Optional[Tuple[float, float, float]] = None

        # subs
        # /tactical/* 用 RELIABLE (tactical_node 默认), /flyeagle/* 多数 BEST_EFFORT
        qos_be = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                            history=HistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(Float64MultiArray, '/tactical/state',
                                 self._cb_state, 10)
        self.create_subscription(Float64MultiArray, '/tactical/debug',
                                 self._cb_debug, 10)
        self.create_subscription(Float64, '/flyeagle/lap_times',
                                 self._cb_lap, qos_be)
        self.create_subscription(Float64, '/flyeagle/lateral_lane_percent',
                                 self._cb_lat, qos_be)
        self.create_subscription(Point, '/flyeagle/collisions',
                                 self._cb_col, qos_be)
        self.create_subscription(PoseStamped, '/flyeagle/ground_truth',
                                 self._cb_pose, qos_be)
        if HAVE_GTA:
            self.create_subscription(GroundTruthArray, '/flyeagle/v2v_ground_truth',
                                     self._cb_v2v, qos_be)

        # pub
        self.action_pub = self.create_publisher(
            Float64MultiArray, '/tactical/rl_action', 1)

        self.get_logger().info('RL bridge ready (HAVE_GTA=%s)' % HAVE_GTA)

    # ---- Callbacks ----
    def _cb_state(self, msg: Float64MultiArray):
        d = msg.data
        if len(d) < 10:
            return
        with self._lock:
            self._obs.ego_s = d[0]
            self._obs.ego_n = d[1]
            self._obs.ego_V = d[2]
            self._obs.ego_chi = d[3]
            self._obs.ego_ax = d[4]
            self._obs.ego_ay = d[5]
            self._obs.w_left = d[6]
            self._obs.w_right = d[7]
            self._obs.curvature = d[8]
            n_opp = int(d[9])
            self._obs.n_opp = n_opp
            opps = []
            idx = 10
            for i in range(n_opp):
                if idx + 4 > len(d):
                    break
                opps.append({
                    'id': i,
                    's': d[idx], 'n': d[idx + 1],
                    'V': d[idx + 2], 'chi': d[idx + 3],
                })
                idx += 4
            self._obs.opps = opps
            self._obs.last_update_t = time.time()

    def _cb_debug(self, msg: Float64MultiArray):
        if len(msg.data) >= 1:
            with self._lock:
                self._obs.fsm_mode = int(msg.data[0])

    def _cb_lap(self, msg: Float64):
        with self._lock:
            self._latest_lap_time = float(msg.data)
            self._lap_time_consumed = False

    def _cb_lat(self, msg: Float64):
        with self._lock:
            self._latest_lat_pct = float(msg.data)

    def _cb_col(self, msg: Point):
        with self._lock:
            self._collision_count += 1
            # x,y axes encode wall vs opponent in collisions topic per metrics_collector
            if abs(msg.x) > 0.5 or abs(msg.y) > 0.5:
                self._collision_opp += 1
            else:
                self._collision_wall += 1

    def _cb_pose(self, msg: PoseStamped):
        with self._lock:
            self._ego_pose = (msg.pose.position.x,
                              msg.pose.position.y,
                              msg.pose.position.z)

    def _cb_v2v(self, msg):  # GroundTruthArray
        with self._lock:
            self._v2v_opps = list(msg.vehicles)

    # ---- Public API ----
    def consume_lap(self) -> Optional[float]:
        with self._lock:
            if self._lap_time_consumed:
                return None
            self._lap_time_consumed = True
            return self._latest_lap_time

    def consume_collisions(self) -> Tuple[int, int, int]:
        """Return (new_total, new_wall, new_opp) since last consume."""
        with self._lock:
            d = self._collision_count - self._collision_seen
            self._collision_seen = self._collision_count
            return d, self._collision_wall, self._collision_opp

    def snapshot(self) -> LatestObs:
        with self._lock:
            # shallow copy
            o = LatestObs(
                ego_s=self._obs.ego_s, ego_n=self._obs.ego_n,
                ego_V=self._obs.ego_V, ego_chi=self._obs.ego_chi,
                ego_ax=self._obs.ego_ax, ego_ay=self._obs.ego_ay,
                w_left=self._obs.w_left, w_right=self._obs.w_right,
                curvature=self._obs.curvature, n_opp=self._obs.n_opp,
                opps=[dict(o) for o in self._obs.opps],
                fsm_mode=self._obs.fsm_mode,
                last_update_t=self._obs.last_update_t,
            )
            return o

    def latest_lat_pct(self) -> float:
        with self._lock:
            return self._latest_lat_pct

    def publish_action(self, action: np.ndarray):
        msg = Float64MultiArray()
        msg.data = [float(x) for x in action]
        self.action_pub.publish(msg)


def spin_bridge_in_thread(node: RLBridgeNode) -> Tuple[MultiThreadedExecutor, threading.Thread]:
    exec_ = MultiThreadedExecutor(num_threads=2)
    exec_.add_node(node)
    t = threading.Thread(target=exec_.spin, daemon=True)
    t.start()
    return exec_, t
