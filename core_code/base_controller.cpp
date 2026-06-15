#include "controller/base_controller.h"
#include "controller/mpc_func.h"
#include "controller/mpcc_func.h"
#include "controller/abs_control_wheel.hpp"
#include <controller/slip_calculation.hpp>
#include <controller/gear_controller.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <utility>

namespace base_controller
{

  float getLongitudinalFbActuation(const Input &input, float *cumul_error_ptr,
                                   ForceRequired *force_ptr, const SlipState &slip_state)
  {
    // Speed Feedback
    float speed_error = input.target_speed - input.speed;
    float kp_speed_error = input.config.kp_long_fb * speed_error;
    float integral_upper_limit =
        std::max((input.config.platform_specs.integral_force_limit_upper -
                  kp_speed_error) /
                     input.config.ki_long_fb,
                 0.0f);
    float integral_lower_limit =
        std::min((input.config.platform_specs.integral_force_limit_lower -
                  kp_speed_error) /
                     input.config.ki_long_fb,
                 0.0f);
    *cumul_error_ptr =
        std::clamp((*cumul_error_ptr + speed_error * input.config.delta_t),
                   integral_lower_limit, integral_upper_limit);

    float ki_cumul_speed_error = input.config.ki_long_fb * (*cumul_error_ptr);
    if (input.reset_integral_force)
      ki_cumul_speed_error = 0;
    float f_speed = kp_speed_error + ki_cumul_speed_error;
    // Slip circle feedback
    // calculate alpha_bar
    float alpha_f = slip_state.slip_angle_f;
    float alpha_r = slip_state.slip_angle_r;

    auto alpha_bar_f = alpha_f / input.config.alpha_f_ref;
    auto alpha_bar_r = alpha_r / input.config.alpha_r_ref;

    float k_f = slip_state.slip_rate_f;
    float k_r = slip_state.slip_rate_r;

    auto k_bar_f = k_f / input.config.k_f_ref;
    auto k_bar_r = k_r / input.config.k_r_ref;
    float f_slip = 0;

    // switch tc on/off
    auto k_gain = input.config.k_gain;
    auto alpha_gain = input.config.alpha_gain;
    if (!input.config.enable_slip_angle_feedback)
    {
      alpha_gain = 0;
      alpha_bar_f = 0;
      alpha_bar_r = 0;
    }
    if (!input.config.enable_slip_ratio_feedback)
    {
      k_gain = 0;
    }
    // if both slips
    if (std::abs(alpha_bar_f) > 1 || std::abs(k_bar_f) >= 1)
    {
      auto delta_k_bar =
          (std::abs(alpha_bar_f) > 1)
              ? std::abs(k_bar_f)
              : (std::abs(k_bar_f) - std::sqrt(1 - alpha_bar_f * alpha_bar_f));
      auto delta_alpha_bar = (alpha_bar_f <= 1) ? 0 : (std::abs(alpha_bar_f) - 1);
      f_slip = k_gain * delta_k_bar + alpha_gain * delta_alpha_bar;
      if (k_bar_f > 0)
      {
        f_slip *= -1;
      }
      // else if only rear slips
    }
    else if (std::abs(alpha_bar_r) > 1 || std::abs(k_bar_r) >= 1)
    {
      auto delta_k_bar =
          (std::abs(alpha_bar_r) > 1)
              ? std::abs(k_bar_r)
              : std::abs(k_bar_r) - std::sqrt(1 - alpha_bar_r * alpha_bar_r);
      auto delta_alpha_bar = (alpha_bar_r <= 1) ? 0 : (std::abs(alpha_bar_r) - 1);
      f_slip = k_gain * delta_k_bar + alpha_gain * delta_alpha_bar;
      if (k_bar_r > 0)
      {
        f_slip *= -1;
      }
    }
    else
    {
      // intentionally left blank for sonar compatibility
    }
    // clamp f_slip according to the sign and max of f_speed
    if (f_speed < 0)
    {
      f_slip = std::clamp(f_slip, 0.0f, -f_speed);
    }
    else
    {
      f_slip = std::clamp(f_slip, -f_speed, 0.0f);
    }
    force_ptr->fb1_p = kp_speed_error;
    force_ptr->fb1_i = ki_cumul_speed_error;
    force_ptr->fb2 = f_slip;
    // return (f_speed + f_slip);
    return f_speed;
  };

  SlipState getSlipState(const Input &input, float last_steer)
  {
    SlipState result;
    float alpha_f = 0;
    float alpha_r = 0;
    if (input.vel_state.v_x >= input.config.min_speed)
    {
      alpha_f = std::atan((input.vel_state.v_y +
                           input.longi_model.a * input.vel_state.r) /
                          input.vel_state.v_x) -
                last_steer;
      alpha_r = std::atan(
          (input.vel_state.v_y - input.longi_model.b * input.vel_state.r) /
          input.vel_state.v_x);
    }
    // calculate k_bar
    float k_f = 0;
    float k_r = 0;
    if (input.vel_state.v_x >=
        input.config.min_speed)
    { // avoid division by zero
      k_f = (input.longi_model.wheel_radius_r *
                 ((input.wheel_speeds.fl + input.wheel_speeds.fr) / 2) -
             input.vel_state.v_x) /
            input.vel_state.v_x;
      k_r = (input.longi_model.wheel_radius_r * input.wheel_speeds.rl -
             input.vel_state.v_x) /
            input.vel_state.v_x;
    }
    result.slip_angle_f = alpha_f;
    result.slip_angle_r = alpha_r;
    result.slip_rate_f = k_f;
    result.slip_rate_r = k_r;
    return result;
  }

  inline float scaleForce(float force, float max_force)
  {
    return force * 100 / max_force;
  }

  float maxForce(float rpm, const LongModel &lm, uint8_t gear)
  {
    return static_cast<float>(
        ((lm.final_ratio * lm.gear_ratios[gear]) / lm.wheel_radius_r) *
        (lm.engine_torque_coeffs.at(0) * std::pow(rpm, 5) +
         lm.engine_torque_coeffs.at(1) * std::pow(rpm, 4) +
         lm.engine_torque_coeffs.at(2) * std::pow(rpm, 3) +
         lm.engine_torque_coeffs.at(3) * std::pow(rpm, 2) +
         lm.engine_torque_coeffs.at(4) * rpm + lm.engine_torque_coeffs.at(5)));
  }

  float getLongitudinalFfwActuation(const Input &input,
                                    ForceRequired *force_ptr)
  {
    double temp_speed = input.speed;
    float f_resistance =
        (temp_speed > input.config.min_speed)
            ? static_cast<float>(
                  input.longi_model.res_a * temp_speed * temp_speed +
                  input.longi_model.res_c + input.longi_model.res_b * temp_speed)
            : 0;
    float f_acceleration = input.longi_model.mass *
                           (input.look_ahead_speed - input.target_speed) /
                           input.config.look_ahead_time_speed;
    force_ptr->ff1 = f_resistance;
    force_ptr->ff2 = f_acceleration;
    return (f_resistance + f_acceleration);
  }

  std::pair<float, float> forceToInputs(const Input &input, const Output &last,
                                        float force, float rpm)
  {
    std::pair<float, float> to_return{};
    if (force > 0)
    {
      // calculate force at max throttle and scale to find necessary throttle
      // find wheel force at th = 1
      float max_force = maxForce(rpm, input.longi_model, last.controls.gear);
      to_return.first = std::max(scaleForce(force, max_force),
                                 input.config.platform_specs.zero_force_throttle);
    }
    else
    {
      if (force > input.config.platform_specs.zero_throttle_force)
      {
        // find necessary brake
        to_return.first =
            input.config.platform_specs.zero_force_throttle *
            (1 - force / input.config.platform_specs.zero_throttle_force);
      }
      else
      {
        to_return.second = std::clamp(
            (-1 * (force - input.config.platform_specs.zero_throttle_force) *
             input.config.kp_brake),
            input.config.platform_specs.brake_limit_lower,
            input.config.platform_specs.brake_limit_upper);
        if(to_return.second == input.config.platform_specs.brake_limit_upper)
        {
          std::cout << "Brake limit reached: " << to_return.second << std::endl;
        }
      }
    }
    return to_return;
  };

  std::pair<float, float> getLongitudinalActuation(const Input &input,
                                                   const Output &last,
                                                   const SlipState &slip_state,
                                                   float *cumul_error_ptr,
                                                   float rpm,
                                                   ForceRequired *force_ptr)
  {
    float last_steer = last.controls.steer;
    float force_long = getLongitudinalFbActuation(input, cumul_error_ptr,
                                                  force_ptr, slip_state) +
                       getLongitudinalFfwActuation(input, force_ptr);
    force_ptr->ft = force_long;
    auto [throttle, brake] = forceToInputs(input, last, force_long, rpm);
    std::pair<float, float> to_return;
    throttle = std::min(
        throttle, last.controls.accel +
                      input.config.throttle_ramp_rate_max * input.config.delta_t);
    to_return.first =
        std::clamp(throttle, input.config.platform_specs.throttle_limit_lower,
                   input.config.platform_specs.throttle_limit_upper);
    to_return.second = brake;
    return to_return;
  };

  float getLateralFbActuation(const Input &input, const SlipState &slip_state)
  {

    auto ss_beta{0.0 + input.longi_model.b * input.path_curvature};

    return input.config.kp_steer_fb *
           static_cast<float>(input.lateral_error +
                              input.config.look_ahead_distance_yaw *
                                  (input.yaw_error + ss_beta));
  };

  float getLateralFfwActuation(const Input &input, const SlipState &slip_state)
  {
    auto ack_wheel_angle{std::atan(input.longi_model.l * input.path_curvature)};

    auto ffw{ack_wheel_angle * input.config.kp_feedforward};

    return ffw;
  };

  float getLateralActuationfromPerception(const Input &input,
                                          SteerRequired *steer_ptr,
                                          float *cumul_yaw_error_ptr)
  {
    const float kp = input.kp_yaw_ctr, ki = 0.001;
    float kp_lat = kp * static_cast<float>(input.yaw_error);
    const float upper = 100.0;
    const float lower = -100.0;
    float integral_upper_limit = std::max((upper - kp_lat) / ki, 0.0f);
    float integral_lower_limit = std::min((lower - kp_lat) / ki, 0.0f);
    *cumul_yaw_error_ptr =
        std::clamp((*cumul_yaw_error_ptr + input.yaw_error * input.config.delta_t),
                   integral_lower_limit, integral_upper_limit);

    if (input.reset_integral_force)
    {
      *cumul_yaw_error_ptr = 0.0;
    }
    float ki_lat = ki * (*cumul_yaw_error_ptr);
    auto fb = -kp_lat; // + ki_lat;
    steer_ptr->fb = fb;
    return std::clamp(fb + input.later_model.steering_offset,
                      -input.later_model.max_wheel_angle,
                      input.later_model.max_wheel_angle);
  };

  float getLateralActuation(const Input &input, const SlipState &slip_state, SteerRequired *steer_ptr)
  {
    auto ffw = getLateralFfwActuation(input, slip_state);
    auto fb = getLateralFbActuation(input, slip_state);

    steer_ptr->fb = fb;
    steer_ptr->ff = ffw;

    return std::clamp(ffw - fb + input.later_model.steering_offset,
                      -input.later_model.max_wheel_angle,
                      input.later_model.max_wheel_angle);
  };

  uint8_t getGearActuation(const Input &input, const Output &last, float rpm,
                           float force_request)
  {
    uint8_t gear = last.controls.gear;
    std::chrono::steady_clock::time_point timenow{};
    static std::chrono::steady_clock::time_point time_last_shift{};
    timenow = std::chrono::steady_clock::now();
    std::vector<float> shift_up_rpm_vec = {6950, 6950, 6950, 6950, 6950, 6950};
    std::vector<float> shift_down_rpm_vec = {4000, 4000, 4400, 4500, 5000, 5500};
    // 获取当前档位的升降档转速阈值
    float shift_up_rpm = shift_up_rpm_vec[gear - 1];
    float shift_down_rpm = shift_down_rpm_vec[gear - 1];

    if (auto time_since_last_shift =
            static_cast<float>(std::chrono::duration_cast<std::chrono::seconds>(
                                   timenow - time_last_shift)
                                   .count());
        time_since_last_shift >= input.config.platform_specs.shift_delay)
    {
      if (rpm >= shift_up_rpm &&
          gear < input.longi_model.gear_ratios.size() - 1 &&
          force_request > 0)
      {
        gear += 1;
        time_last_shift = std::chrono::steady_clock::now();
      }
      else if (rpm < shift_down_rpm &&
               gear > 1 && force_request <= 0)
      {
        gear -= 1;
        time_last_shift = std::chrono::steady_clock::now();
      }
      else if (input.target_speed > input.config.min_speed &&
               gear == 0)
      {
        gear = 1;
        time_last_shift = std::chrono::steady_clock::now();
      }
    }
    return gear;
  }

  // 动力系统参数结构体

  MPC_Output getMPC(const Input &input, const Output &last)
  {
    // 记录MPC开始时间
    auto mpc_start_time = std::chrono::high_resolution_clock::now();
    MPC_Output mpc_output;

    static float mpc_ts = input.mpc_params.mpc_ts; 

    static int predict_step = input.mpc_params.mpc_prediction_horizon;      
    static int mpc_look_ahead_index = input.mpc_params.mpc_look_ahead_index;
    static NMPC1 nmpc(predict_step, mpc_ts, input);
    
    static int predict_step_lowspeed = 11;  
    static int mpc_look_ahead_index_lowspeed = 1;
    static Input input_lowspeed = input;
    input_lowspeed.mpc_params.m_Q_00 = 6;
    static NMPC1 nmpc_lowspeed(predict_step_lowspeed, mpc_ts, input_lowspeed);
    // nmpc.update_params(predict_step, mpc_ts, input);

    Eigen::Matrix<float, 3, Eigen::Dynamic> desired_states(3, predict_step);
    Eigen::Matrix<float, 2, Eigen::Dynamic> desired_controls(2, predict_step);
    Eigen::Vector3f states; 
    Eigen::Matrix<float,2,1> controls;
    

    states << 0, 0, 0; // 车体坐标系下当前的位置和航向角为0
    controls << input.target_speed, last.controls.steer;
    // printf("last.controls.steer: %f\n", last.controls.steer);
    
    for (int i = 0; i < predict_step; ++i) {
        desired_states(0, i) = input.mpc_reference_data.x_ref[i + mpc_look_ahead_index];
        desired_states(1, i) = input.mpc_reference_data.y_ref[i + mpc_look_ahead_index];
        desired_states(2, i) = input.mpc_reference_data.yaw_ref[i + mpc_look_ahead_index];
        desired_controls(0, i) = input.mpc_reference_data.vel_ref[i + mpc_look_ahead_index];
        desired_controls(1, i) = std::atan(input.mpc_reference_data.r_ref[i + mpc_look_ahead_index] / (input.mpc_reference_data.vel_ref[i + mpc_look_ahead_index] + 0.1) * input.mpc_params.mpc_car_l);
    }
    // 循环求解
    float mpc_solve_status = 0.0;
    std::vector<Eigen::Matrix<float, 2, 1>> control_sequence;
    std::vector<Eigen::Matrix<float, 5, 1>> predict_trajectory;
    static bool use_lowspeed_mpc = true;
    // 滞回上下阈值
    const float mpc_hyst_lower = 4.0f;
    const float mpc_hyst_upper = 10.0f;

    // 更新滞回状态
    if (use_lowspeed_mpc) {
      if (input.speed > mpc_hyst_upper) {
        use_lowspeed_mpc = false;
      }
    } else {
      if (input.speed < mpc_hyst_lower) {
        use_lowspeed_mpc = true;
      }
    }

    if (!use_lowspeed_mpc) // 使用高速 NMPC
    {
        nmpc.opti_solution(states, controls, desired_states, desired_controls, input); // 优化求解
        control_sequence = nmpc.get_controls();
        predict_trajectory = nmpc.get_predict_trajectory();
        mpc_solve_status = nmpc.get_mpc_solve_status();
    }
    else // 使用低速 NMPC（更长预测步长）
    {
        desired_states.resize(3, predict_step_lowspeed);
        desired_controls.resize(2, predict_step_lowspeed);
        for (int i = 0; i < predict_step_lowspeed; ++i) {
            desired_states(0, i) = input.mpc_reference_data.x_ref[i + mpc_look_ahead_index_lowspeed];
            desired_states(1, i) = input.mpc_reference_data.y_ref[i + mpc_look_ahead_index_lowspeed];
            desired_states(2, i) = input.mpc_reference_data.yaw_ref[i + mpc_look_ahead_index_lowspeed];
            desired_controls(0, i) = input.mpc_reference_data.vel_ref[i + mpc_look_ahead_index_lowspeed];
            desired_controls(1, i) = std::atan(input.mpc_reference_data.r_ref[i + mpc_look_ahead_index_lowspeed] / (input.mpc_reference_data.vel_ref[i + mpc_look_ahead_index_lowspeed] + 0.1f) * input.mpc_params.mpc_car_l);
        }
        // 只调用一次求解
        nmpc_lowspeed.opti_solution(states, controls, desired_states, desired_controls, input);
        control_sequence = nmpc_lowspeed.get_controls();
        predict_trajectory = nmpc_lowspeed.get_predict_trajectory();
        mpc_solve_status = nmpc_lowspeed.get_mpc_solve_status();
    }

    std::vector<base_controller::PredictedPoint> predicted_points;
    for (const auto& point : predict_trajectory) {
        base_controller::PredictedPoint predicted_point;
        predicted_point.x = point[0];
        predicted_point.y = point[1];
        predicted_point.yaw = point[2];
        predicted_point.v = point[3];
        predicted_point.delta = point[4];
        predicted_points.push_back(predicted_point);
    }

    // 记录MPC结束时间
    auto mpc_end_time = std::chrono::high_resolution_clock::now();
    auto mpc_solve_time = std::chrono::duration_cast<std::chrono::milliseconds>(mpc_end_time - mpc_start_time).count();
    mpc_output.control_sequence = control_sequence;
    mpc_output.predicted_points = predicted_points;
    mpc_output.mpc_debug.mpc_solve_status = mpc_solve_status;
    mpc_output.mpc_debug.mpc_solve_time = mpc_solve_time;

    return mpc_output;
  };
  /**
   * @brief 油门与扭矩比例之间的映射函数，支持正向和逆向映射。
   * 
   * @param input_value 输入值，可以是油门指令（0.0 ~ 1.0）或扭矩比例（0.0 ~ 1.0）。
   * @param is_forward 是否为正向映射（默认为 true）。如果为 true，则从油门指令映射到扭矩比例；
   *                   如果为 false，则从扭矩比例映射到油门指令。
   * @return float 返回映射后的值。如果输入值超出范围，则返回边界值。
   */
  float throttleToTorqueMap(const Input &input,float input_value, bool is_forward = true) {
      // 根据方向选择映射表
      const std::vector<float>& x = is_forward ? input.powertrain.throttleMapInput : input.powertrain.throttleMapOutput;
      const std::vector<float>& y = is_forward ? input.powertrain.throttleMapOutput : input.powertrain.throttleMapInput;
      // 检查输入是否有效
      if (x.size() != y.size() || x.empty()) {
          throw std::invalid_argument("Invalid input for throttle-to-torque mapping");
      }
      // 限制输入值到范围内
      input_value = std::clamp(input_value, x.front(), x.back());

      // 查找对应区间并进行线性插值
      for (size_t i = 1; i < x.size(); ++i) {
          if (input_value >= x[i - 1] && input_value <= x[i]) {
              float t = (input_value - x[i - 1]) / (x[i] - x[i - 1]);
              return y[i - 1] + t * (y[i] - y[i - 1]);
          }
      }
      // 如果未找到区间，返回边界值
      return (input_value < x.front()) ? y.front() : y.back();
  }
  /**
   * @brief 计算发动机输出的扭矩值
   * 
   * @param rpm 发动机转速（单位：RPM），会被限制在发动机的最小和最大转速范围内
   * @param throttle_cmd 油门指令（范围：0.0 ~ 1.0），表示油门的开度
   * 
   * @return float 发动机输出的扭矩值（单位：Nm）
   */
  float getEngineTorque(const Input &input, float throttle_cmd) {
      // 限制转速
      float current_rpm = std::clamp(input.engine_speed, input.powertrain.engineRpmMin, input.powertrain.engineRpmMax);
      // 使用整合的映射函数 - 正变换
      float TxR_factor = throttleToTorqueMap(input,throttle_cmd, true);
      // 发动机多项式
      float T_max = 0;
      for (int i = 0; i < 6; ++i) {
          T_max += input.powertrain.enginePoly[i] * std::pow(current_rpm, 5 - i);
      }
      // 总扭矩 = throttle * 多项式 - 摩擦损耗
      float T_combustion = TxR_factor * T_max - input.powertrain.engineFrictionTorque;
      return T_combustion;
  }
  /**
   * @brief 计算车辆在当前条件下的安全油门值。
   * 
   * @param input 包含车辆状态和动力学模型的输入结构体。
   * @param current_gear 当前档位，用于确定传动比。
   * @param predicted_accy 预测的侧向加速度，用于计算车辆稳定性。
   * @param ay_max_vehicle 整车的最大侧向加速度，用于限制纵向加速度。
   * 
   * @return float 返回限制后的安全油门值（范围：0.0 ~ 100.0）。
   */
  float getSafeThrottle(const Input &input, int current_gear, float predicted_accy ,float ay_max_vehicle, float base_resistance) 
  {
      float current_rpm = std::clamp(input.engine_speed, input.powertrain.engineRpmMin, input.powertrain.engineRpmMax);
      // 基本参数
      const float gravity = 9.81f;
      const float transmission_efficiency = 0.81f; // 拟合的传动效率
                 
      // 计算传动比
      float gear_ratio = input.powertrain.gearRatios[current_gear-1];
      float total_ratio = gear_ratio * input.powertrain.finalGearRatio;
      
      // 计算后轮载荷分配比例
      float rear_axle_load_ratio = input.longi_model.b / (input.longi_model.a + input.longi_model.b);                                                 
      // 1. 计算整车和后轮的侧向加速度极限
      float ay_max_rear = ay_max_vehicle * rear_axle_load_ratio ;
      
      // 2. 椭圆模型计算后轮纵向加速度极限

      float ay_rear_current = std::abs(predicted_accy * rear_axle_load_ratio ); // 当前侧向加速度，考虑到车辆的稳定性和安全性
      float ay_ratio = std::clamp(ay_rear_current / ay_max_rear, -1.0f, 1.0f);
      float ax_rear_safe_max = ay_max_rear * std::sqrt(1.0f - ay_ratio * ay_ratio);
      
      // 3. 计算全油门下的发动机扭矩和驱动力
      float T_net_full = getEngineTorque(input, 1.0f);
      
      float F_drive_full = T_net_full * total_ratio * transmission_efficiency / input.longi_model.wheel_radius_r;
      
      // 4. 计算安全的最大驱动力和油门限制
      float F_rear_safe_max = ax_rear_safe_max * input.longi_model.mass - base_resistance;
      float TxR_safe_max = (F_drive_full > 0) ? 
          std::min(F_rear_safe_max / F_drive_full, 1.0f) : 0.0f;
      
      // 5. 使用整合的映射函数 - 逆变换
      float throttle_safe_max = throttleToTorqueMap(input,TxR_safe_max, false) * 100.0f;
      throttle_safe_max = std::clamp(throttle_safe_max, 5.0f, 100.0f);
      
      return throttle_safe_max;
  }

  Kalman_Filter kf_steer(0.00001, 0.001);
  uint8_t gear_new = 0;
  int gear_status = -1;
  bool predict_downshift_flag = false;

  // -----------------------------------------------------------------------------
  // [NMPCC 升级] 横纵向统一 NMPC: 构造 + 单步求解封装
  // 输入: input (含 mpc_reference_data + ego_x/ego_y/yaw_angle)
  //       last  (上一步 steer 用作 δ 初值)
  // 输出: 第一步 (a_cmd, δ_cmd), 求解时间, 求解状态
  // -----------------------------------------------------------------------------
  struct MPCCResult
  {
    float a_cmd      = 0.0f;
    float delta_cmd  = 0.0f;
    float solve_status = 0.0f;
    float solve_time_ms = 0.0f;
    std::vector<PredictedPoint> predicted_points;
  };

  MPCCResult runMPCC(const Input &input, const Output &last)
  {
    MPCCResult res;
    static int N      = std::max(8, input.mpc_params.mpcc_N);
    static float dt   = (input.mpc_params.mpcc_dt > 1e-3f) ? input.mpc_params.mpcc_dt : 0.05f;
    static NMPCC nmpcc(N, dt, input);

    // 参考点不足时不解
    if (static_cast<int>(input.mpc_reference_data.x_ref.size()) < N + 2) {
      return res;
    }

    // ---- 把全局参考线转换到车体系 (避免 NMPCC 数值病态) ----
    Eigen::Matrix<float, 4, Eigen::Dynamic> ref_body(4, N);
    const float cy = std::cos(input.yaw_angle), sy = std::sin(input.yaw_angle);
    // 限制 v_ref 不要远离当前 vx, 否则 q_vel*(vx-v_ref)^2 主导让 IPOPT 解极端 a
    const float vx_now = std::max(0.0f, input.vel_state.v_x);
    const float vref_lo = std::max(0.0f, vx_now - 2.0f);
    const float vref_hi = vx_now + 10.0f;   // 一窗 (N*dt) 最多多 10 m/s
    for (int k = 0; k < N; ++k) {
      const float xg   = input.mpc_reference_data.x_ref[k + 1];
      const float yg   = input.mpc_reference_data.y_ref[k + 1];
      const float pg   = input.mpc_reference_data.yaw_ref[k + 1];
      float vref = input.mpc_reference_data.vel_ref[k + 1];
      vref = std::clamp(vref, vref_lo, vref_hi);
      const float dx = xg - input.ego_x;
      const float dy = yg - input.ego_y;
      ref_body(0, k) =  cy * dx + sy * dy;
      ref_body(1, k) = -sy * dx + cy * dy;
      ref_body(2, k) = pg - input.yaw_angle;
      ref_body(3, k) = vref;
    }

    // ---- 初始状态 (车体系) ----
    Eigen::Matrix<float, 8, 1> x0;
    x0.setZero();
    x0(3) = std::max(0.1f, input.vel_state.v_x);
    x0(4) = input.vel_state.v_y;
    x0(5) = input.vel_state.r;
    x0(6) = last.controls.steer;
    x0(7) = 0.0f;

    nmpcc.solve(x0, ref_body, input);

    res.solve_status   = nmpcc.solve_status();
    res.solve_time_ms  = nmpcc.solve_time_ms();
    auto u0 = nmpcc.first_control();
    res.a_cmd     = u0(0);
    res.delta_cmd = u0(1);

    auto preds = nmpcc.predicted_traj();
    for (auto &p : preds) {
      PredictedPoint q;
      // 转回全局便于可视化
      q.x   = input.ego_x + cy * p(0) - sy * p(1);
      q.y   = input.ego_y + sy * p(0) + cy * p(1);
      q.yaw = p(2) + input.yaw_angle;
      q.v   = p(3);
      q.delta = p(4);
      res.predicted_points.push_back(q);
    }
    return res;
  }

  Output getControls(const Input &input, const Output &last)
  {
    Output output;
    output.valid = false;
    output.cumul_speed_error = last.cumul_speed_error;
    output.cumul_lateral_error = last.cumul_lateral_error;
    output.cumul_yaw_error = last.cumul_yaw_error;
    output.slip_state = getSlipState(input, last.controls.steer);
    ForceRequired force_request;
    Input input_copy = input;
    static MPC_Output mpc_output;
    static int control_predictIndex = 0;
    static float speed_mpc = 0.0f;
    static float steer_mpc = 0.0f;
    output.mpc_debug.mpc_speed = 0;
    output.mpc_debug.mpc_steer = 0;
    output.mpc_debug.mpc_solve_status = 0;
    output.mpc_debug.mpc_solve_time = 0;
    if (input.mpc_params.mpc_flag) // 根据 MPC_flag 判断是否使用 MPC
    {
        if (input.mpc_params.mpc_smoothFilter_flag) {
          // 根据速度调整稳定性权重
          input_copy.mpc_params.mpc_control_horizon = (input.speed > 25.0) ? 3 : 2;
        }
        if (control_predictIndex % input_copy.mpc_params.mpc_control_horizon == 0) 
        {
            control_predictIndex = 0;
            mpc_output = getMPC(input_copy, last);
        }
        
        if (!mpc_output.control_sequence.empty() && control_predictIndex < mpc_output.control_sequence.size()) 
        {
            speed_mpc = mpc_output.control_sequence[control_predictIndex][0];
            steer_mpc = mpc_output.control_sequence[control_predictIndex][1];
        } 
        else 
        {
            // 处理 predict_control_sequence 为空或 control_predictIndex 超出范围的情况
            speed_mpc = 0.0f;
            steer_mpc = 0.0f;
            output.mpc_debug.mpc_solve_status = 0;
        }
        output.mpc_debug.mpc_speed = speed_mpc;
        output.mpc_debug.mpc_steer = steer_mpc;
        output.mpc_debug.mpc_solve_status = mpc_output.mpc_debug.mpc_solve_status;
        output.mpc_debug.mpc_solve_time = mpc_output.mpc_debug.mpc_solve_time;
        output.mpc_debug.current_mpc_control_horizon = input_copy.mpc_params.mpc_control_horizon;
        
        if(output.mpc_debug.mpc_solve_time > 50)
        {
         output.mpc_debug.mpc_solve_status = 0;
         std::cout << "Warning: MPC solve time too long: " << output.mpc_debug.mpc_solve_time << " ms" << std::endl;
        }
        output.predict_trajectory = mpc_output.predicted_points;
        // input_copy.target_speed = speed_mpc;
        control_predictIndex++;
    }
    // ~

    
    float rpm = std::clamp(input.engine_speed, input.longi_model.rpm_lower,
                           input.longi_model.rpm_upper);
    auto [throttle, brake] = getLongitudinalActuation(
      input_copy, last, output.slip_state, &output.cumul_speed_error, rpm, &force_request);

    
    output.force_req = force_request;
    if (std::isnan(throttle) || std::isnan(brake))
      return output;

    float lat_actuation;
    // if (!input.gps_conf)
    // {
    //   lat_actuation = getLateralActuationfromPerception(input, &output.steer_req, &output.cumul_yaw_error);
    // }
    // else
    // {
    //   lat_actuation = getLateralActuation(input, output.slip_state, &output.steer_req);
    // }

    lat_actuation = getLateralActuation(input, output.slip_state, &output.steer_req);
    if (std::isnan(lat_actuation))
      return output;
    auto gear_actuation = getGearActuation(input, last, rpm, force_request.ft);

    if (input.config.enable_new_gear_logic)
    {
      static GearShiftController gear_controller;
      gear_controller.set_feedback_gear(input.gear_ack);
      gear_controller.set_feedback_omega_engine(input.engine_speed);
      gear_controller.set_feedback_trajectory(input.trajectory_info.reference_path, input.trajectory_info.current_index);
      a2rl_bs_msgs::msg::EgoState ego_state;
      ego_state.velocity.x = input.vel_state.v_x;
      ego_state.velocity.y = input.vel_state.v_y;
      ego_state.acceleration.x = input.acc_x;
      ego_state.acceleration.y = input.acc_y;
      gear_controller.set_feedback_ego_state(ego_state);
      gear_controller.set_predicted_gear_flag(true);
      gear_controller.step();
      gear_new = gear_controller.get_gear_command();
      gear_status = gear_controller.get_gear_status();
      predict_downshift_flag = gear_controller.get_downshift_flag();
      // std::cout << "gear_old = " << static_cast<int>(gear_actuation) << ", gear_new = " << static_cast<int>(gear_new) << ", gear_ack = " << static_cast<int>(input.gear_ack) << std::endl;
    }

    output.controls.steer_raw = lat_actuation;
    output.controls.steer_kf = kf_steer.GetValue(lat_actuation);

    // if (input.start_kalman_filter)
    // {
    //   output.controls.steer = output.controls.steer_kf;
    // }
    // else
    // {
    //   output.controls.steer = output.controls.steer_raw;
    // }

    // 转向
    if (input.mpc_params.mpc_flag && output.mpc_debug.mpc_solve_status == 1 && input.local_flag != 1)
    {
      output.controls.steer = steer_mpc;
      output.mpc_debug.use_mpc = true;
    }
    else
    {
      output.controls.steer = output.controls.steer_raw;
      output.mpc_debug.use_mpc = false;
    }

    // ============================================================================
    // [NMPCC 升级] 横纵向统一 NMPC: 同时覆写 steer 与 (throttle, brake)
    //   仅在 mpcc_flag 启用 + 求解成功 + 非 pit/local_flag 模式 下接管。
    //   求解失败时静默回退到上方原 MPC + PID 路径，保证安全。
    // ============================================================================
    bool mpcc_active = false;
    // 低速保护: NMPCC 在 vx<10 时模型奇异/参考速度差太大, 退回 PID+横向 MPC
    if (input.mpc_params.mpcc_flag && input.local_flag != 1 && input.speed >= 10.0f)
    {
      static MPCCResult mpcc_res;
      static int mpcc_pred_idx = 0;
      const int mpcc_horizon = std::max(1, input.mpc_params.mpc_control_horizon);
      if (mpcc_pred_idx % mpcc_horizon == 0) {
        mpcc_pred_idx = 0;
        mpcc_res = runMPCC(input, last);
      }
      mpcc_pred_idx++;

      // 节流日志: 每 ~50 帧 (~5s) 一条
      static int mpcc_log_cnt = 0;
      if ((++mpcc_log_cnt % 50) == 0) {
        std::cout << "[NMPCC] vx=" << input.speed
                  << " status=" << mpcc_res.solve_status
                  << " a=" << mpcc_res.a_cmd
                  << " delta=" << mpcc_res.delta_cmd
                  << " solve=" << mpcc_res.solve_time_ms << "ms" << std::endl;
      }

      // 防御: 解出来的 a 必须在合理范围, 否则 fallback (避免 brake=1.2e7)
      const bool a_sane = std::isfinite(mpcc_res.a_cmd) && std::abs(mpcc_res.a_cmd) <= 9.0f;
      const bool d_sane = std::isfinite(mpcc_res.delta_cmd) && std::abs(mpcc_res.delta_cmd) <= 0.6f;
      if (mpcc_res.solve_status == 1.0f && a_sane && d_sane)
      {
        mpcc_active = true;
        // 1) 横向: 直接用 NMPCC 的 δ
        output.controls.steer = mpcc_res.delta_cmd;
        output.mpc_debug.use_mpc = true;
        output.mpc_debug.mpc_steer = mpcc_res.delta_cmd;
        output.mpc_debug.mpc_solve_status = 1.0f;
        output.mpc_debug.mpc_solve_time = mpcc_res.solve_time_ms;
        // 2) 纵向: 由 a_cmd 计算总驱动力 F_x = m·a + F_resist(v),
        //    再调用既有 forceToInputs(...) 反查 throttle/brake. 输入输出协议不变.
        const float v = std::max(0.0f, input.speed);
        const float f_resist = (v > input.config.min_speed)
            ? input.longi_model.res_a * v * v + input.longi_model.res_c + input.longi_model.res_b * v
            : 0.0f;
        const float f_long = input.longi_model.mass * mpcc_res.a_cmd + f_resist;
        force_request.ff1 = f_resist;
        force_request.ff2 = input.longi_model.mass * mpcc_res.a_cmd;
        force_request.fb1_p = 0.0f;
        force_request.fb1_i = 0.0f;
        force_request.fb2 = 0.0f;
        force_request.ft = f_long;
        auto [th_mpcc, br_mpcc] = forceToInputs(input, last, f_long, rpm);
        // 油门 ramp (沿用既有限制)
        th_mpcc = std::min(
            th_mpcc, last.controls.accel + input.config.throttle_ramp_rate_max * input.config.delta_t);
        throttle = std::clamp(th_mpcc, input.config.platform_specs.throttle_limit_lower,
                              input.config.platform_specs.throttle_limit_upper);
        brake = br_mpcc;
        if (!output.predict_trajectory.empty() == false || !mpcc_res.predicted_points.empty()) {
          output.predict_trajectory = mpcc_res.predicted_points;
        }
      }
      else
      {
        // MPCC 求解失败：保留原有 PID + 横向 MPC 的解 (已在上面赋值)
        output.mpc_debug.mpc_solve_status = 0.0f;
      }
    }
    (void)mpcc_active;
    // 油门约束
    // 前馈
    float predicted_accy = std::tan(-(last.controls.steer*0.85)) * (0.83*input.speed+0.4) * input.speed / input.longi_model.l;
    // ggv边界
    static float ay_max_vehicle = 0.002  * input.speed * input.speed + 0.094 * input.speed + 11.943;
    static float base_resistance = -1.04765f * input.speed * input.speed + 47.5f * input.speed - 1609.73f;
    static float safe_ratio = 0.85f;
    auto throttle_safemax = getSafeThrottle(input, gear_actuation, predicted_accy, ay_max_vehicle * safe_ratio,base_resistance);
    output.mpc_debug.throttle_safemax = throttle_safemax;
    // throttle = std::min(throttle, throttle_safe_max);
    // 反馈
    if (abs(output.slip_state.slip_angle_r) > 0.07)
    {
      throttle = std::min(throttle, 5.0f);
    }
    if (input.speed < 15.0)
    {
      throttle = std::min(throttle, 65.0f);
    }
     // 计算滑移率
    static SlipCalculation slip_calculation;
    static FirstOrderLowPass<DataPerWheel<double>> slip_angle_filter{DataPerWheel<double>{0.0}, DataPerWheel<double>{0.7}};
    static FirstOrderLowPass<DataPerWheel<double>> slip_rate_filter{DataPerWheel<double>{0.0}, DataPerWheel<double>{0.7}};
    a2rl_bs_msgs::msg::EgoState ego_state_abs;
    ego_state_abs.acceleration.x = input.acc_x;
    ego_state_abs.velocity.x = input.vel_state.v_x;
    ego_state_abs.velocity.y = input.vel_state.v_y;
    ego_state_abs.angular_rate.z = input.vel_state.r;
    slip_calculation.set_feedback_egostate(ego_state_abs);
    slip_calculation.set_feedback_brake_pressure_Pa(input.brake_pressure_);
    slip_calculation.set_feedback_steering_rad(static_cast<double>(last.controls.steer));
    DataPerWheel<double> wheel_speeds_radps{
        input.wheel_speeds.fl, input.wheel_speeds.fr, input.wheel_speeds.rl, input.wheel_speeds.rr};
    slip_calculation.set_feedback_wheelspeed_radps(wheel_speeds_radps);
    slip_calculation.set_wheelspeed_ok(true);
    slip_calculation.step();
    // 获取滑移率计算结果
    DataPerWheel<double> slip, slip_rate, slip_angle, slip_lookahead, slip_rate_filtered, filtered_slip_angle;
    slip = slip_calculation.get_wheelslips();
    slip_angle = slip_calculation.get_slip_angles();
    slip_rate = (slip - last.slip) / 0.01;
    slip_rate_filtered = slip_rate_filter.step(slip_rate);
    slip_lookahead = slip + slip_rate_filtered * 0.00; // 0.00s lookahead
    filtered_slip_angle = slip_angle_filter.step(slip_angle);
    output.slip = slip;
    output.slip_angle = slip_angle;
    // ABS计算
    // 处理输入数据并计算
    static DataPerWheel<AbsTcInputs> abs_inputs;
    static DataPerWheel<ABSControlledWheel> abs_controlled_wheels{
        ABSControlledWheel{Wheel_Position::Front_Left}, ABSControlledWheel{Wheel_Position::Front_Right},
        ABSControlledWheel{Wheel_Position::Rear_Left}, ABSControlledWheel{Wheel_Position::Rear_Right}};
    static SlipControlInputs slip_control_inputs;
    slip_control_inputs.slip_valid = true;
    slip_control_inputs.long_fx = force_request.ft - input.config.platform_specs.zero_throttle_force;
    slip_control_inputs.twist.linear.x = input.vel_state.v_x;
    slip_control_inputs.slip_input_abs = slip;
    DataPerWheel<double> target_brake_pressure{brake, brake, brake * (1 - input.brake_bias) / input.brake_bias, 
                                                  brake * (1 - input.brake_bias) / input.brake_bias};
    slip_control_inputs.target_brake_pressure = target_brake_pressure;
    slip_control_inputs.slip_lookahead_abs = slip_lookahead;
    slip_control_inputs.slip_angle_abs = filtered_slip_angle;
    slip_control_inputs.slip_rate_abs = slip_rate_filtered;
    for (size_t i = 0; i < abs_controlled_wheels.size(); i++)
    {
      abs_inputs[i].long_fx = std::clamp(slip_control_inputs.long_fx, -24000.0, 24000.0);
      abs_inputs[i].slip = slip_control_inputs.slip_input_abs[i];
      abs_inputs[i].slip_valid = slip_control_inputs.slip_valid;
      abs_inputs[i].twist = slip_control_inputs.twist;
      abs_inputs[i].brake_pressure = slip_control_inputs.target_brake_pressure[i];
      abs_inputs[i].slip_lookahead = slip_control_inputs.slip_lookahead_abs[i];
      abs_inputs[i].slip_angle = std::abs(slip_control_inputs.slip_angle_abs[i]);
      abs_inputs[i].slip_rate = slip_control_inputs.slip_rate_abs[i];
      abs_inputs[i].allowed = input.config.enable_abs; // 允许 ABS 控制
      abs_controlled_wheels[i].set_abs_inputs(abs_inputs[i]);
      abs_controlled_wheels[i].step();
    }
    // 获取计算结果
    DataPerWheel<bool> is_latched;
    DataPerWheel<float> abs_brake_pressure;
    for (size_t i = 0; i < abs_controlled_wheels.size(); i++)
    {
      is_latched[i] = abs_controlled_wheels[i].get_is_latched();
      abs_brake_pressure[i] = static_cast<float>(abs_controlled_wheels[i].get_target_brake_pressure());
      if(is_latched[i])
      {
        std::cout << "ABS activated on wheel " << i << std::endl;
      }
    }

    output.abs_wheel_latched = is_latched;
    output.controls.abs_brake_pressure = abs_brake_pressure;
    output.controls.accel = throttle;
    output.controls.brake = brake;
    
    if(input.config.enable_new_gear_logic)
    {
      output.controls.gear = gear_new;
      output.gear_status.downshift_flag = predict_downshift_flag;
      output.gear_status.gear_status = gear_status;
    }
    else
    {
      output.controls.gear = gear_actuation;
    }

    output.lateral_error = input.lateral_error;
    output.yaw_error = input.yaw_error;
    output.speed_error = input.target_speed - input.speed;

    output.valid = true;
    return output;
  };

} // namespace base_controller
