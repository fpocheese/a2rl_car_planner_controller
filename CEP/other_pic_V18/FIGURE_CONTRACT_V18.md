# Figure contract — V18 physical track bounds

- Core question: where does the published tactical corridor lie relative to
  the physical left and right track boundaries at each displayed station?
- Existing evidence: retain corridor fill/edges, Ego and Opponent paths, and
  all event markers and separation annotations from V17.
- Added evidence: plot physical (n_L(s)) and (n_R(s)) using the same grey
  dashed style and represent both with one `Track bound` legend entry.
- Integrity: recorded boundaries are interpolated to the existing plotting
  grid without smoothing; raw data and the displayed corridor are unchanged.
- Scope: modify only the two `path_corridor` panels; copy all remaining V17
  PNGs unchanged.
- Geometry and typography: retain the 89 x 57 mm corridor canvas and LaTeX
  NewTX typography.
- Export: 600-dpi PNG only.
