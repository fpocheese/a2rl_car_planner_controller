# CEP manuscript package

This folder contains the revised manuscript prepared with Elsevier's
`elsarticle` class in the journal-required `final,5p,times,twocolumn` layout
for *Control Engineering Practice*.

## Build

From this directory, run:

```bash
pdflatex -interaction=nonstopmode -halt-on-error a2rl_paper.tex
pdflatex -interaction=nonstopmode -halt-on-error a2rl_paper.tex
```

The checked build produces a 14-page `a2rl_paper.pdf` with resolved citations
and cross-references. The artwork is deliberately stored in the same directory
as the manuscript source because Elsevier Editorial Manager does not preserve
source subdirectories.

## Main files

- `a2rl_paper.tex`: CEP-formatted main manuscript.
- `method_execution_condensed.tex`: three-subsection tactical method and a
  concise common-execution section containing the core SOCP, speed-profile,
  and MPCC equations plus executable pseudocode.
- `simulation_results_refined.tex`: HIL testbed, protocol, case evidence, and
  validity boundary, including the complete execution, tracking/tactical, and
  supporting clearance/tire-force-envelope figure sets for both
  representative regimes.
- `comparison_tables.tex`: matched baselines and tactical ablations.
- `references.tex`: cited-only bibliography used in the rendered manuscript.
- `highlights.txt`: separate editable highlights file; all four bullets satisfy
  the journal's 85-character limit.
- `elsarticle.cls`, `elsarticle-num.bst`, and
  `elsarticle-template-num.tex`: files from Elsevier's official numbered
  article template bundle.
- `Eav24_default.json`: supplied EAV24 plant and sensor configuration.
- `rgs-8805gc-industrial-rugged-hpc-server.pdf`: supplied RGS-8805GC product
  datasheet.
- `case_02.json` and `case_05.json`: closed-loop logs used for the two revised
  representative engagements. `case_04_trimmed.json` is retained as a legacy
  case log but is not used in the revised main-text evaluation.
- `final0205_case_02_*.pdf` and `final0205_case_05_*.pdf`: final editable-vector
  panels for the two representative engagements.
- `plot_path_corridors.py` and `plot_representative_panels.py`: legacy
  three-case plotting utilities retained for provenance; they do not reproduce
  the supplied `final0205` artwork byte-for-byte.
- `plot_compact_osr_summary.py`: legacy aggregate-OSR diagnostic retained for
  provenance. The revised manuscript reports its effect-size information
  directly in the comparison and ablation tables.
- `verify_representative_cases.py`: reproducible check of the two-row
  representative case-summary table against the case-02 and case-05 logs.
- `reported_aggregate_results.json`: machine-readable, author-confirmed source
  for the headline, comparison, ablation, and seed-summary values.
- `verify_reported_aggregates.py`: verifies success counts, the exact interval,
  Holm-adjusted proportion tests, and every numeric cell in Tables 2 and 3.
- `REPORTED_RESULTS_PROVENANCE.md`: aggregate provenance, current audit scope,
  and the explicit rule against reconstructing per-lap observations.
- `reference_implementation/`: tested executable reconstruction of the
  game-guided TQC action, IBR, FSM, corridor, and training-loss equations.
- `SOURCE_DATA_MANIFEST.md`: evidence provenance and current archive boundary.
- `DATA_REPOSITORY_PLAN.md`: DOI-ready data/code deposit structure and the
  unresolved author fields.
- `TERMINOLOGY_LEDGER.md`: canonical technical vocabulary used across the
  manuscript.
- `IMPLEMENTATION_EVIDENCE_AUDIT.md`: checkpoint/source audit, author-attested
  method--result linkage, executable reconstruction, and later archival work.
- `REVIEW_AND_SUBMISSION_CHECKLIST.md`: one-context adversarial review and the
  author inputs still required before submission.

## Template and scope sources

- Elsevier LaTeX instructions: <https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions>
- Control Engineering Practice scope: <https://shop.elsevier.com/journals/control-engineering-practice/0967-0661>
- Control Engineering Practice Guide for Authors:
  <https://www.sciencedirect.com/journal/control-engineering-practice/publish/guide-for-authors>

The paper's HIL section is written to address the journal's requirement that a
simulation-only study demonstrate a representative genuine application. It
separates the evidence for representativeness from the remaining sim-to-track
limitations.

The required separate highlights file and the generative-AI disclosure are
included. A graphical abstract is encouraged rather than required and has not
been created. The journal prohibits generative-AI-created manuscript artwork;
all supplied manuscript figures therefore remain author/source generated.

## Verification

From this directory, the current checks are:

```bash
python3 verify_representative_cases.py
python3 verify_reported_aggregates.py
python3 -m unittest discover -s reference_implementation/tests -p 'test_reference.py'
```

The PyTorch-specific TQC loss test is run in an environment with PyTorch using
`python -m unittest discover -s reference_implementation/tests -p 'test_tqc.py'`.
