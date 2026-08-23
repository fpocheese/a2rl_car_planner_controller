# Source-data manifest

## Included evidence

| File | Role in the manuscript |
|---|---|
| `Eav24_default.json` | Auditable configuration evidence for the EAV24 plant, actuators, CAN input mode, sensors, aerodynamics, suspension, and tire model. |
| `../fig_tire/plot_vn_transformer_tire_curves.py` | Reproducible Magic Formula evaluation for the single-column 1-by-2 load-dependent tire-force panel in Fig. 2; exports editable PDF/SVG and 600-dpi raster files. |
| `../fig_tire/relabel_model_pdf.py` | Reproducible text-only vector edit that updates the legacy handling label in the supplied vehicle-model PDF without changing its geometry. |
| `rgs-8805gc-industrial-rugged-hpc-server.pdf` | Product-family evidence for the target RGS-8805GC industrial computer. It does not identify the CPU/GPU actually installed in the evaluated unit. |
| `case_02.json` | Representative high-speed-closure run. |
| `case_05.json` | Representative sharp-corner side-by-side run. |
| `case_04_trimmed.json` | Legacy equal-speed mixed-curvature log retained in the package but not used in the revised two-case main-text evaluation. |
| `final0205_case_02_*.pdf`, `final0205_case_05_*.pdf` | Supplied editable-vector artwork for all panels in the revised representative-case section. The displayed corridor-history, FSM-normalization, and tire-envelope masks are disclosed in the corresponding captions and main text. |
| `plot_path_corridors.py` | Legacy utility for the earlier three-case path/corridor panels; it is retained for provenance and does not reproduce the supplied `final0205` artwork byte-for-byte. |
| `plot_representative_panels.py` | Legacy utility for the earlier three-case panel set; it is retained for provenance and is not presented as the source of the final `final0205` figures. |
| `overtake_case_metrics_case02_case05.csv` | Original compact metric export for representative Cases I and II. |
| `verify_representative_cases.py` | Standard-library-only audit script that recomputes the two revised case-summary rows directly from the JSON logs and checks the manuscript's rounded values. |
| `reported_aggregate_results.json` | Canonical machine-readable record of the author-confirmed headline, comparison, ablation, and seed-summary aggregates. It contains no reconstructed lap-level samples. |
| `verify_reported_aggregates.py` | Recomputes OSR counts, the exact binomial interval, two-proportion tests, Holm adjustments, and checks all numeric entries in the comparison and ablation LaTeX tables. |
| `plot_compact_osr_summary.py` | Legacy aggregate-OSR diagnostic retained for provenance. The revised manuscript reports the percentage-point deficits directly in Tables 2 and 3. |
| `REPORTED_RESULTS_PROVENANCE.md` | Defines the author-attestation basis, current verification scope, non-synthesis rule, and later per-lap archive requirements. |
| `reference_implementation/` | Tested executable reconstruction of the reported game-guided TQC tactical layer. It is equation-level reference code, not a byte-identical historical source archive. |
| `case_02_engagement_snapshots.pdf`, `case_05_engagement_snapshots.pdf`, `case_04_engagement_snapshots.pdf` | Legacy four-phase engagement figures retained for provenance; the revised manuscript uses the two-panel `final0205` figures. |
| `compact_osr_summary.pdf` | Legacy output retained for provenance but no longer included in the revised manuscript. No synthetic lap observations were used. |

## Identified checkpoint and implementation evidence classes

The two main-text case logs identify the TQC checkpoint recorded in
`IMPLEMENTATION_EVIDENCE_AUDIT.md`. Inspection of the checkpoint establishes a
27-dimensional dynamic observation, two 12-dimensional fixed-track previews,
a 10-dimensional action, two 25-atom critics, and 46 retained target atoms.

Running `python verify_representative_cases.py` from this directory verifies
the two rows in the representative-case table. The overtake interval is
measured consistently in both cases, from first entry into `OVERTAKE` to the
first later sample with `Delta_s < 0`.

The authors confirm that the reported HIL campaigns used the game-guided TQC
method described in the manuscript. Because the exact historical training
tree remains on the temporarily inaccessible server, the included
`reference_implementation/` reconstructs the equations and verifies that the
IBR prior, robust-value target, tire-force-aware action projection, FSM,
carver, and 46-atom TQC loss form an executable system. Training-only game modules are deliberately
separated from its standard actor/critic inference export. The unrelated
hybrid-PPO prototype found elsewhere in the project is retained as historical
context but is not used as provenance for this paper.

## Aggregate comparison record and boundary

The authors confirm that the August manuscript values are the true aggregates
for the evaluation described in the paper. They are now stored in
`reported_aggregate_results.json`, including integer success counts, and the
verification script establishes their statistical and cross-file consistency.
Older files named `comparison_results.json` and `ablation_results.json`, dated
19 June 2026, contain different values and are intentionally not presented as
source data for the author-confirmed August campaigns.

The current aggregate record does not expose the per-lap scenario/seed
hierarchy. The per-lap files remain on the temporarily inaccessible remote
server and have not been synthesized from the aggregate tables. After access
is restored, the authors should deposit those records and the exact historical
training/evaluation archive according to `DATA_REPOSITORY_PLAN.md`.
