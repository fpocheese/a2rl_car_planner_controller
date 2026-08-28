# V18 QA notes

## Scope

- Exactly two single-panel PNGs differ from V17:
  `case_02_path_corridor.png` and `case_05_path_corridor.png`.
- The remaining twelve single-panel PNGs and the combined 3D GG PNG are
  byte-identical to V17.
- Both revised panels are exported at 600 dpi from the accepted 89 x 57 mm
  canvas.

## Boundary integrity

- Case 02 left bound: 6.679--6.850 m; right bound: -6.838---6.702 m;
  minimum physical width: 13.401 m.
- Case 05 left bound: 5.590--7.473 m; right bound: -7.896---5.657 m;
  minimum physical width: 11.436 m.
- All samples are finite, ego progress is strictly increasing and no left/right
  inversion occurs.
- Physical boundaries are interpolated to the existing display grid without
  smoothing.
- Both physical boundaries use the same grey dashed style and one shared
  `Track bound` legend entry; no left/right style distinction is encoded.

## Existing corridor versus physical bounds

- The unchanged Case 02 display corridor remains fully within the physical
  bounds.
- The unchanged Case 05 display corridor extends at most 0.178 m beyond the
  recorded right physical bound. This small pre-existing discrepancy is now
  visible because V18 adds the physical-boundary evidence. V18 deliberately
  does not clip or alter the accepted V17 corridor processing.

## Export contract

- This package follows the accepted V17 PNG-only contract. The generic static
  validator's SVG/PDF requirement is therefore intentionally overridden.
