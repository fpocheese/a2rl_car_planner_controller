# IEEE Sensors Journal belief-space paper reconstruction

## Objective
Reconstruct the non-experimental content of `a2rl_paper.tex` around the chain:
LiDAR opponent detection -> delay-compensated Frenet opponent-state belief ->
belief-space overtaking game -> risk-consistent tactical corridor ->
deterministic path/speed planning and MPCC.

## Boundaries
- Do not modify `simulation_results_refined.tex`.
- Do not generate or invent sensing-noise, latency, or dropout results.
- Use only existing verified bibliography keys.
- Preserve Magic Formula and GGV, but make planning/control execution modules
  rather than independent contributions.

## Completion criteria
- Requested title, abstract, section structure, terminology, and TODO comments.
- One belief symbol `\mathcal B_k` used consistently after its definition.
- Sensing uncertainty and latency affect the game before corridor construction.
- Game chance constraint and corridor margin share the same risk allocation.
- Current framework figure updated to the three requested layers.
- LaTeX compiles without new undefined references, labels, or layout errors.
- `simulation_results_refined.tex` SHA-256 remains
  `2173b5895d8434c5951b6f39b6a4fb5a1443d54777603301f4b40a2b65d17ce2`.
