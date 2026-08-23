# Terminology ledger

This ledger fixes the canonical vocabulary used across the CEP manuscript.

| Canonical term | First-use definition or role | Usage decision |
|---|---|---|
| game-guided tactical corridor policy | Proposed learned tactical module | Use for the complete proposed tactical method; `proposed method` is permitted in tables/results after first use. |
| Stackelberg game with iterative best responses (IBR) | Structural interaction model | Expand once; use `Stackelberg--IBR` when naming the combined construction. |
| Truncated Quantile Critics (TQC) | Distributional off-policy RL algorithm | Expand once; use `TQC` thereafter. |
| tactical corridor | Time-varying Frenet lateral bounds plus speed cap | Do not substitute `trajectory` or `path`, which are downstream execution objects. |
| tire-force feasibility envelope | Speed-dependent vehicle-level acceleration constraint derived from load-dependent tire-force characteristics | Use the full term at first occurrence and `tire-force envelope` thereafter; do not replace it with the broader phrase `tire performance`. |
| tire-force envelope utilization $\rho$ | Combined normal/tangential demand normalized by the available tire-force limits | Feasible actions and measured responses satisfy $\rho\le1$. |
| map-conditioned features | Curvature and width previews queried from the fixed track map | The policy input remains curvature/width based; tire-force feasibility enters through state-dependent action projection and critic evaluation. |
| finite-state machine (FSM) | Hysteretic tactical mode logic | Expand once; mode names use small capitals in LaTeX. |
| execution layer | Shared corridor-constrained planner, speed profiler, MPCC, and actuator allocator | Planning and control are not separate novelty claims. |
| hardware-in-the-loop (HIL) | Target computer and separate simulator connected through virtual CAN | Expand once; use `HIL` thereafter. |
| EAV24 plant | Configured simulator-side vehicle model | Distinguish from the reduced internal vehicle model and the physical race car. |
| virtual CAN | Simulator/target-computer CAN transport used in the experiment | Do not call it a physical electrical CAN-bus test. |
| overtaking success rate (OSR) | Fraction of laps satisfying the stated pass criterion | Use `OSR` after first definition. |
| time to overtake (TTO) | Reported overtake timing metric | Use `TTO` after first definition. |
| time to collision (TTC) | Reported proximity-risk metric | Use `TTC` after first definition. |
| path-feasibility ratio (PFR) | Fraction of planning cycles returning a feasible SOCP solution | Use `PFR` after first definition. |
| model predictive contouring controller (MPCC) | Shared low-level path/speed tracking controller | Use `MPCC` after first definition. |

The terms `full method` and `without ...` are retained only as experimental
condition labels. They do not replace the canonical method name in explanatory
prose.
