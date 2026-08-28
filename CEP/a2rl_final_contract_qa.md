# CEP final-method contract QA

Generated: 2026-08-24

## Deliverables and build

- TeX: `a2rl_paper.tex`
- PDF: `a2rl_paper.pdf`
- TeX SHA-256: `60c3258adf3bba5782d6a849c2828ec21843f58b295ba09fe6f03cf2da94defd`
- PDF SHA-256: `9483d4b1629cacded4c383d74c100ed6092bc536b00d6b3b8d528e5f2574fdff`
- Full `pdflatex -interaction=nonstopmode -halt-on-error` build: PASS (two stable final passes)
- Undefined references/citations: 0
- Duplicate labels: 0 (87 labels, all unique)
- Overfull boxes: 0
- LaTeX/natbib/font/PDF-version warnings: 0

## Length and final-page comparison

- Before: 14 pages, 5,073,191 bytes.
- After: 14 pages, 5,086,612 bytes.
- Net page-count change: 0 pages.
- Before final-page content bbox: y = 82.464--743.479 pt (78.516% of page height).
- After final-page content bbox: y = 82.464--744.053 pt (78.584% of page height).
- Final-page vertical-extent change: +0.574 pt (+0.068 percentage points); no stranded or half-empty page.

## Added labels (18)

- `eq:bound_projection`
- `eq:controller_executable_cap`
- `eq:deterministic_fsm`
- `eq:duel_observation`
- `eq:frenet_domain`
- `eq:fsm_guards`
- `eq:game_candidate_bank`
- `eq:game_label_dataset`
- `eq:game_utility`
- `eq:lock_update`
- `eq:longitudinal_limits`
- `eq:mode_corridor_map`
- `eq:opponent_preview`
- `eq:planner_executable_cap`
- `eq:preview_curvature`
- `eq:response_set_teacher`
- `eq:reward_features`
- `eq:tire_parameter_map`

## Deleted labels (116)

Most deleted labels belonged to the removed inactive method archive; the rest
belonged to the removed dynamic-bicycle propagation and tire-characteristics
figure.

- `eq:abort`
- `eq:action_smooth_reward`
- `eq:alphaf`
- `eq:alphar`
- `eq:approach_reward`
- `eq:atan`
- `eq:backward_init`
- `eq:brake_map`
- `eq:carver_map`
- `eq:cone`
- `eq:corr_ineq`
- `eq:corridor_init`
- `eq:corridor_smooth_reward`
- `eq:ecos_form`
- `eq:ego_ctrl`
- `eq:ego_prog`
- `eq:ego_race`
- `eq:ego_safe`
- `eq:ego_tactical_decision`
- `eq:ego_term`
- `eq:ema`
- `eq:fade`
- `eq:fb_accel_available`
- `eq:fb_brake_available`
- `eq:fd`
- `eq:follower_response`
- `eq:follower_utility`
- `eq:force_req`
- `eq:forward_init`
- `eq:fsm`
- `eq:fsm_modes`
- `eq:game_policy_map`
- `eq:game_value_loss`
- `eq:guidance_tuple`
- `eq:hybrid_action_game`
- `eq:ibr_decision`
- `eq:ibr_update`
- `eq:min_corridor_width`
- `eq:mpcc_ec`
- `eq:mpcc_el`
- `eq:mpcc_enu`
- `eq:mpcc_epsi`
- `eq:mpcc_ic`
- `eq:mpcc_model`
- `eq:mpcc_nlp`
- `eq:mpcc_ref`
- `eq:normalization`
- `eq:obs`
- `eq:obs_ego`
- `eq:obs_opp`
- `eq:overtake_bound`
- `eq:path_affine_model`
- `eq:path_arclength`
- `eq:path_cart`
- `eq:path_decision`
- `eq:path_initial`
- `eq:planner_corridor_intersection`
- `eq:planner_grid`
- `eq:planner_pipeline`
- `eq:prior_mse`
- `eq:prior_statistics`
- `eq:pseudogradient`
- `eq:rdot`
- `eq:ready`
- `eq:reference_tuple`
- `eq:response_neighborhood`
- `eq:reward_collision`
- `eq:reward_crush`
- `eq:reward_lateral`
- `eq:reward_overtaken`
- `eq:reward_pass`
- `eq:reward_sbs`
- `eq:reward_wide`
- `eq:rho_exc`
- `eq:rl_blend_max`
- `eq:rl_blend_min`
- `eq:rl_blend_w`
- `eq:robust_tactical_value`
- `eq:safe_mask`
- `eq:safety_clip`
- `eq:side_sign`
- `eq:slin_conv`
- `eq:socp`
- `eq:steer_ff`
- `eq:tactical_objective`
- `eq:tanh_map`
- `eq:terminal_mode`
- `eq:terminal_slack`
- `eq:throttle_map`
- `eq:time_reconstruct`
- `eq:tire`
- `eq:tire_envelope_factor`
- `eq:tire_preview_demand`
- `eq:tqc_actor`
- `eq:tqc_critic`
- `eq:tqc_target`
- `eq:track_aug_obs`
- `eq:track_prior`
- `eq:trap`
- `eq:ttc`
- `eq:utility_decomposition`
- `eq:vbwd`
- `eq:vfwd`
- `eq:vi_equilibrium`
- `eq:vlim_iter`
- `eq:vmerge`
- `eq:vxdot`
- `eq:vydot`
- `eq:yaw_rate_map`
- `fig:mode_defend`
- `fig:mode_overtake`
- `fig:mode_race_hold`
- `fig:mode_shadow`
- `fig:tire_characteristics`
- `subsec:obs_encoding`
- `subsec:tqc_optimization`

## Contract acceptance

1. Sections 2--4 rewritten and global terminology synchronized: PASS.
2. Inactive `\iffalse...\fi` method archive physically removed: PASS.
3. Dynamic-bicycle candidate propagation removed: PASS.
4. Tire-characteristics Figure, label, source reference, and PDF asset removed: PASS.
5. Final page count does not exceed the baseline: PASS (14 -> 14).
6. Forbidden legacy terms return zero matches in the requested `rg` search: PASS.
7. Required response-set/RC-NMPC terminology is used consistently: PASS.
8. Action chain `raw -> B -> F` is consistent; `F` is a tactical action: PASS.
9. Speed-cap chain `req -> F -> {P,C}` is consistent: PASS.
10. Fixed tire capacities have no undefined speed argument: PASS.
11. Environment replay `D` and teacher dataset `D_g` are distinct: PASS.
12. Every robust-value label is paired with its own `a_g^F`: PASS.
13. FSM cases produce one state by explicit priority; health/abort and post-pass precede Shadow/Overtake: PASS.
14. Side-lock release is limited to abort, post-pass, or health failure: PASS.
15. Positive-Frenet-left carver directions are consistent: PASS.
16. Speed reference is `V_k^r`; first controller command is `(V_{0|t}^{c*},delta_{0|t}^{c*})`: PASS.
17. RC-NMPC cap constrains optimized speed-command variables, not measured speed: PASS.
18. Tire admissibility is limited to the reference level; realized demand is diagnostic: PASS.
19. Experiment/result numerical multiset is unchanged: PASS.
20. No equilibrium-recovery, formal-safety, recursive-feasibility, measured-speed-bound, push-forward-entropy, or isolated robust-head ablation claim remains: PASS.
21. All 22 citations resolve and all 22 bibliography entries are cited: PASS.
22. Visual contact-sheet review found no equation spill, clipped figure, stranded heading, or half-empty page: PASS.

Overall: PASS (22/22).
