# other_pic_V18

V18 preserves the complete V17 PNG package and changes only:

- `single_panels/case_02_path_corridor.png`
- `single_panels/case_05_path_corridor.png`

## Added spatial information

Each path-corridor panel now includes the physical track bounds expressed in
the same Frenet coordinates as the corridor and vehicle paths:

- upper (n_L(s)) and lower (n_R(s)): identical dark-grey dashed lines;
- the two curves share one concise legend entry, **Track bound**.

For legacy Case 02, the bounds are reconstructed from the recorded
`W_left/W_right` values at each ego station. For Case 05, the recorded
`track_left/track_right` arrays are used directly. Both are interpolated only
onto the existing corridor display grid; no smoothing or source-data change is
applied.

The corridor, Ego/Opponent paths, Start/Encounter/Pass markers, event
annotations and all V17 processing remain unchanged. All other V18 PNGs are
byte-identical copies of V17. V17 is preserved unchanged.

## Reproduce the modified panels

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/other_pic_v18_mpl \
python3 other_pic_V18/generate_corridor_panels_v18.py
```
