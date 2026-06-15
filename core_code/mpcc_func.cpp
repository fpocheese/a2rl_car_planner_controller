// =============================================================================
//  mpcc_func.cpp -- NMPCC 求解器实现
// -----------------------------------------------------------------------------
//  数学公式（每个预测阶段 k = 0..N-1, 共 N 步）
//
//  连续动力学 (动力学单轨 + 线性轮胎):
//      α_f = atan((vy + lf·r)/(vx+ε)) - δ
//      α_r = atan((vy - lr·r)/(vx+ε))
//      Fyf = -Cf·α_f                    (线性轮胎, 适合小角度区间)
//      Fyr = -Cr·α_r
//      ṗx  = vx·cos(ψ) - vy·sin(ψ)
//      ṗy  = vx·sin(ψ) + vy·cos(ψ)
//      ψ̇   = r
//      v̇x  = a + r·vy - Fyf·sin(δ)/m
//      v̇y  = (Fyf·cos(δ) + Fyr)/m - r·vx
//      ṙ   = (lf·Fyf·cos(δ) - lr·Fyr) / Iz
//      δ̇   = δ_dot   (input)
//      ṡ   = vx        (路径进度近似 = 纵向速度)
//
//  离散化: Explicit RK4, 步长 dt
//
//  代价 (k=0..N-1):
//      L_k = q_lat·e_lat^2 + q_yaw·e_yaw^2 + q_vel·(vx-v_ref)^2
//          + R_a·a^2 + R_dd·δ̇^2 + slack_w·s_fric^2
//    末端: + 进度奖励 -q_progress·s_N
//    其中
//      e_lat = -sin(ψ_ref)·(px-x_ref) + cos(ψ_ref)·(py-y_ref)
//      e_yaw = ψ - ψ_ref
//
//  软约束 (摩擦圆 / g-g 极限, 仅限后轴):
//      (m·a)^2 + (Cr·α_r)^2 ≤ (μ·Fz_r)^2 + s_fric^2,   s_fric ≥ 0
//      Fz_r = m·g·lf/(lf+lr)
//
//  盒约束:
//      a ∈ [ax_min, ax_max]
//      δ ∈ [-δ_max, δ_max]      (作为 state, 通过 δ̇ 与 box on δ 共同强制)
//      δ̇ ∈ [-dd_max, dd_max]
//      vx∈ [0, v_max]
//
//  IPOPT warm-start: 上一步控制序列向前移位 1 步作为初始猜测。
// =============================================================================

#include "controller/mpcc_func.h"
#include <chrono>
#include <cmath>

NMPCC::NMPCC(int N, float dt, const base_controller::Input &input)
: rclcpp::Node("nmpcc_node"), N_(N), dt_(dt)
{
  // 车辆几何
  lf_     = input.longi_model.a;
  lr_     = input.longi_model.b;
  mass_   = input.longi_model.mass;
  // 转动惯量: Eav24 实测 ≈ 1500 kg·m²; 若未提供单独参数, 用经验近似 m·lf·lr
  Iz_     = (input.mpc_params.mpcc_Iz > 0.0f) ? input.mpc_params.mpcc_Iz
                                              : mass_ * lf_ * lr_;
  Cf_     = input.mpc_params.mpcc_Cf;
  Cr_     = input.mpc_params.mpcc_Cr;
  mu_     = input.mpc_params.mpcc_mu;
  g_      = 9.81f;

  q_lat_       = input.mpc_params.mpcc_q_lat;
  q_yaw_       = input.mpc_params.mpcc_q_yaw;
  q_vel_       = input.mpc_params.mpcc_q_vel;
  q_progress_  = input.mpc_params.mpcc_q_progress;
  R_a_         = input.mpc_params.mpcc_R_a;
  R_dd_        = input.mpc_params.mpcc_R_dd;
  slack_w_     = input.mpc_params.mpcc_slack_w;

  ax_max_   = input.mpc_params.mpcc_ax_max;
  ax_min_   = input.mpc_params.mpcc_ax_min;
  v_max_    = input.mpc_params.mpc_max_speed;
  delta_max_= input.mpc_params.mpc_max_wheel_angle_deg * M_PI / 180.0f;
  dd_max_   = input.mpc_params.mpcc_dd_max;

  build_solver();
  // warm-start container
  warm_x_.assign(2 * N_ + N_, 0.0);  // [a_0..a_{N-1}, dd_0..dd_{N-1}, s_fric_0..]
}

void NMPCC::build_solver()
{
  using casadi::SX;
  using casadi::Slice;

  const int nx = 8;   // px,py,psi,vx,vy,r,delta,s
  const int nu = 2;   // a, dd
  const int ns = 1;   // 摩擦圆 slack (per stage)

  SX X = SX::sym("X", nx, N_ + 1);
  SX U = SX::sym("U", nu, N_);
  SX S = SX::sym("S", ns, N_);   // slack per stage (≥0)

  // 参数: x0(8) + 4*N (x_ref, y_ref, psi_ref, v_ref per stage)
  SX P = SX::sym("P", nx + 4 * N_);

  // 连续动力学 lambda
  auto f_dyn = [this](SX x, SX u) -> SX {
    SX px   = x(0);
    SX py   = x(1);
    SX psi  = x(2);
    SX vx   = x(3);
    SX vy   = x(4);
    SX r    = x(5);
    SX delta= x(6);
    SX s    = x(7);
    SX a    = u(0);
    SX dd   = u(1);

    // 防 vx≈0 病态: 加 ε
    SX vx_safe = vx + 0.5;   // 大于 0 的偏置, 低速段平滑
    SX alpha_f = atan((vy + lf_ * r) / vx_safe) - delta;
    SX alpha_r = atan((vy - lr_ * r) / vx_safe);
    SX Fyf = -Cf_ * alpha_f;
    SX Fyr = -Cr_ * alpha_r;

    SX dpx  = vx * cos(psi) - vy * sin(psi);
    SX dpy  = vx * sin(psi) + vy * cos(psi);
    SX dpsi = r;
    SX dvx  = a + r * vy - Fyf * sin(delta) / mass_;
    SX dvy  = (Fyf * cos(delta) + Fyr) / mass_ - r * vx;
    SX dr   = (lf_ * Fyf * cos(delta) - lr_ * Fyr) / Iz_;
    SX ddel = dd;
    SX ds   = vx;
    return SX::vertcat({dpx, dpy, dpsi, dvx, dvy, dr, ddel, ds});
  };

  // RK4 step
  auto rk4 = [&](SX x, SX u) -> SX {
    SX k1 = f_dyn(x, u);
    SX k2 = f_dyn(x + 0.5 * dt_ * k1, u);
    SX k3 = f_dyn(x + 0.5 * dt_ * k2, u);
    SX k4 = f_dyn(x + dt_ * k3, u);
    return x + (dt_ / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4);
  };

  // 初始状态约束
  SX g = SX::vertcat({});
  g = SX::vertcat({g, X(Slice(), 0) - P(Slice(0, nx))});

  // shooting 约束 + cost
  SX cost = 0;
  const SX Fz_r = mass_ * g_ * lf_ / (lf_ + lr_);
  const SX mu_Fz = mu_ * Fz_r;

  for (int k = 0; k < N_; ++k) {
    SX xk = X(Slice(), k);
    SX uk = U(Slice(), k);
    SX xk1 = X(Slice(), k + 1);

    // shooting
    g = SX::vertcat({g, xk1 - rk4(xk, uk)});

    // 当前预测点
    SX px_k  = xk1(0);
    SX py_k  = xk1(1);
    SX psi_k = xk1(2);
    SX vx_k  = xk1(3);
    // SX delta_k = xk1(6);   // 已通过 box-on-state 约束

    // 参考点 (k 对应预测的第 k+1 步)
    int ref_off = nx + 4 * k;
    SX x_ref   = P(ref_off + 0);
    SX y_ref   = P(ref_off + 1);
    SX psi_ref = P(ref_off + 2);
    SX v_ref   = P(ref_off + 3);

    SX e_lat = -sin(psi_ref) * (px_k - x_ref) + cos(psi_ref) * (py_k - y_ref);
    SX e_yaw = psi_k - psi_ref;
    SX e_vel = vx_k - v_ref;

    cost += q_lat_ * e_lat * e_lat
          + q_yaw_ * e_yaw * e_yaw
          + q_vel_ * e_vel * e_vel
          + R_a_   * uk(0) * uk(0)
          + R_dd_  * uk(1) * uk(1)
          + slack_w_ * S(0, k) * S(0, k);

    // 摩擦圆软约束: (m·a)^2 + (Cr·α_r)^2 - (μ·Fz_r + s)^2 ≤ 0
    SX vy_k = xk1(4);
    SX r_k  = xk1(5);
    SX vx_safe = vx_k + 0.5;
    SX alpha_r_k = atan((vy_k - lr_ * r_k) / vx_safe);
    SX rhs = (mu_Fz + S(0, k)) * (mu_Fz + S(0, k));
    SX lhs = (mass_ * uk(0)) * (mass_ * uk(0)) + (Cr_ * alpha_r_k) * (Cr_ * alpha_r_k);
    g = SX::vertcat({g, lhs - rhs});   // ≤ 0
  }

  // 末端进度奖励 (MPCC 创新点): -q_progress · s_N
  cost += -q_progress_ * X(7, N_);

  // 决策变量打包
  SX z = SX::vertcat({SX::reshape(X, -1, 1), SX::reshape(U, -1, 1), SX::reshape(S, -1, 1)});

  casadi::SXDict nlp = {{"x", z}, {"f", cost}, {"g", g}, {"p", P}};
  casadi::Dict opts;
  opts["expand"] = true;
  opts["ipopt.print_level"]      = 0;
  opts["print_time"]             = 0;
  opts["ipopt.max_iter"]         = 60;
  opts["ipopt.acceptable_tol"]   = 1e-3;
  opts["ipopt.acceptable_obj_change_tol"] = 1e-3;
  opts["ipopt.max_cpu_time"]     = 0.04;
  opts["ipopt.warm_start_init_point"] = "yes";
  opts["ipopt.mu_strategy"]      = "adaptive";

  solver_ = casadi::nlpsol("nmpcc_solver", "ipopt", nlp, opts);
}

void NMPCC::solve(const Eigen::Matrix<float, 8, 1> &x0_body,
                  const Eigen::Matrix<float, 4, Eigen::Dynamic> &ref_body,
                  const base_controller::Input & /*input*/)
{
  using casadi::DM;
  auto t0 = std::chrono::steady_clock::now();

  const int nx = 8, nu = 2, ns = 1;

  // ---------- 参数向量 ----------
  std::vector<double> P(nx + 4 * N_, 0.0);
  for (int i = 0; i < nx; ++i) P[i] = x0_body(i);
  for (int k = 0; k < N_; ++k) {
    P[nx + 4 * k + 0] = ref_body(0, k);
    P[nx + 4 * k + 1] = ref_body(1, k);
    P[nx + 4 * k + 2] = ref_body(2, k);
    P[nx + 4 * k + 3] = ref_body(3, k);
  }

  // ---------- 决策变量边界 ----------
  const int n_X = nx * (N_ + 1);
  const int n_U = nu * N_;
  const int n_S = ns * N_;
  const int n_z = n_X + n_U + n_S;
  std::vector<double> lbx(n_z, -1e20), ubx(n_z, 1e20);

  // X box (state):  x[k] = [px,py,psi,vx,vy,r,delta,s]
  for (int k = 0; k <= N_; ++k) {
    int off = k * nx;
    lbx[off + 3] = 0.0;            // vx >= 0
    ubx[off + 3] = v_max_;         // vx <= v_max
    lbx[off + 6] = -delta_max_;    // |δ| <= δ_max
    ubx[off + 6] =  delta_max_;
  }
  // 初始状态在等式约束里固定; 可不再 narrow 此处box 以避免冲突

  // U box: a, dd
  for (int k = 0; k < N_; ++k) {
    int off = n_X + k * nu;
    lbx[off + 0] = ax_min_;
    ubx[off + 0] = ax_max_;
    lbx[off + 1] = -dd_max_;
    ubx[off + 1] =  dd_max_;
  }
  // S ≥ 0
  for (int k = 0; k < N_; ++k) {
    int off = n_X + n_U + k * ns;
    lbx[off + 0] = 0.0;
    ubx[off + 0] = 1e20;
  }

  // ---------- g 约束边界 ----------
  // g = [ x0_eq(8), shoot_eq(8*N), friction_ineq(N) ]
  std::vector<double> lbg, ubg;
  lbg.reserve(nx + nx * N_ + N_);
  ubg.reserve(nx + nx * N_ + N_);
  for (int i = 0; i < nx; ++i)               { lbg.push_back(0.0);    ubg.push_back(0.0); }
  for (int k = 0; k < N_; ++k)
    for (int i = 0; i < nx; ++i)             { lbg.push_back(0.0);    ubg.push_back(0.0); }
  for (int k = 0; k < N_; ++k)               { lbg.push_back(-1e20);  ubg.push_back(0.0); }

  // ---------- 初值 (warm start) ----------
  std::vector<double> z0(n_z, 0.0);
  // X 部分: 用初始状态填充全部 (粗略)
  for (int k = 0; k <= N_; ++k) {
    int off = k * nx;
    for (int i = 0; i < nx; ++i) z0[off + i] = x0_body(i);
  }
  // U 部分: 移位上次解
  if (static_cast<int>(warm_x_.size()) >= 2 * N_) {
    for (int k = 0; k < N_; ++k) {
      int src_a = (k + 1 < N_) ? (k + 1) : (N_ - 1);
      z0[n_X + k * nu + 0] = warm_x_[src_a];
      z0[n_X + k * nu + 1] = warm_x_[N_ + src_a];
    }
  }
  // S 部分 = 0

  // ---------- 求解 ----------
  std::map<std::string, DM> arg;
  arg["x0"]  = z0;
  arg["lbx"] = lbx;
  arg["ubx"] = ubx;
  arg["lbg"] = lbg;
  arg["ubg"] = ubg;
  arg["p"]   = P;

  std::map<std::string, DM> res;
  bool ok = false;
  try {
    res = solver_(arg);
    ok = true;
  } catch (std::exception &e) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                         "NMPCC solver exception: %s", e.what());
    ok = false;
  }

  auto t1 = std::chrono::steady_clock::now();
  solve_time_ms_ = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count() / 1000.0f;

  if (!ok) {
    solve_status_ = 0.0f;
    return;
  }

  // 解析返回
  std::vector<double> sol = std::vector<double>(res.at("x"));
  if (static_cast<int>(sol.size()) != n_z) {
    solve_status_ = 0.0f;
    return;
  }

  // 检查 IPOPT 状态
  std::string st = solver_.stats().count("return_status") ?
                   solver_.stats().at("return_status").as_string() : "unknown";
  bool ok_status = (st == "Solve_Succeeded" || st == "Solved_To_Acceptable_Level");
  solve_status_ = ok_status ? 1.0f : 0.0f;

  // 取第一步控制
  first_u_(0) = static_cast<float>(sol[n_X + 0]);
  // 第一步 δ 用积分: δ_0 = δ_prev + dt * δ̇_0  (state[6] at k=1)
  first_u_(1) = static_cast<float>(sol[1 * nx + 6]);

  // warm-start 更新: 保存 [a_0..,δd_0..]
  warm_x_.assign(2 * N_, 0.0);
  for (int k = 0; k < N_; ++k) {
    warm_x_[k]      = sol[n_X + k * nu + 0];
    warm_x_[N_ + k] = sol[n_X + k * nu + 1];
  }

  // 预测轨迹
  predicted_.clear();
  predicted_.reserve(N_ + 1);
  for (int k = 0; k <= N_; ++k) {
    Eigen::Matrix<float, 5, 1> p;
    int off = k * nx;
    p(0) = sol[off + 0];
    p(1) = sol[off + 1];
    p(2) = sol[off + 2];
    p(3) = sol[off + 3];   // vx
    p(4) = sol[off + 6];   // δ
    predicted_.push_back(p);
  }
}
