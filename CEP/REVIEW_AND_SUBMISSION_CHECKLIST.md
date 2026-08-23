# Adversarial review and submission checklist

This is one source-grounded reviewer report produced in a single context.
Mutual blindness between multiple reviewers was not available, so it is not
presented as a three-reviewer consensus or an editorial decision.

## Overall assessment

The revision now has a defensible academic spine. The central contribution is
the game-guided tactical corridor policy, while planning and control form one
fixed execution layer. The HIL section directly addresses the practical remit
of *Control Engineering Practice* by documenting target hardware, a separate
EAV24 plant server, a dual virtual-CAN boundary, four actuator outputs, plant
subsystems, timing, and explicit sim-to-track limits. The comparison and
ablation design is potentially strong. The authors have now confirmed the
reported method and aggregate results, and the package contains both a
manuscript-aligned executable implementation and a machine-readable aggregate
record with reproducible statistical checks. The remaining submission risks
concern archival traceability, protocol/timing detail, and administrative
metadata rather than an unresolved choice about the paper's scientific story.

## Major concerns

### R1-M1. Per-lap aggregate archive remains to be deposited

- Axis: data-resource quality and statistical rigor
- Severity: Major
- Blocking: Yes for final data deposition; no for continued manuscript development
- Claim pointer: the abstract, HIL evaluation, and comparison tables report
  947 successes in 1000 laps, zero collisions, and the listed baseline and
  ablation results.
- Evidence pointer: `simulation_results_refined.tex`, repeated-evaluation
  paragraph; Tables `tab:comparison` and `tab:ablation`;
  `SOURCE_DATA_MANIFEST.md`.
- Concern: the authors confirm that the printed values are the true campaign
  aggregates, and `reported_aggregate_results.json` plus
  `verify_reported_aggregates.py` now reproduce the count arithmetic,
  interval, tests, and LaTeX tables. The per-lap records remain on a temporarily
  inaccessible remote server, however, so scenario/seed clustering and
  event-level provenance cannot yet be independently audited. Older June files
  remain excluded because they are not the author-confirmed August record.
- Resolution test: identify the canonical campaign and its date, code commit,
  model/checkpoint IDs, scenario IDs, and seed IDs; archive one row per lap;
  regenerate every aggregate table, confidence interval, hypothesis test, and
  bar figure from a versioned analysis script; retain a checksum manifest.

### R1-M2. Evaluation protocol is under-specified

- Axis: experimental design and reproducibility
- Severity: Major
- Blocking: No
- Claim pointer: all methods are said to use a matched 1000-lap scenario
  schedule.
- Evidence pointer: `simulation_results_refined.tex`, subsection
  `Evaluation protocol and reported quantities`.
- Concern: the scenario allocation, sampling distributions for initial gap,
  speed and lateral offset, numerical evaluation horizon, opponent-policy
  definitions and versions, checkpoint selection rule, and seed-to-lap mapping
  are not reported. TTO censoring and the precise collision/contact event rule
  also need definition.
- Resolution test: add a compact protocol table and a deterministic campaign
  manifest that reproduces all 1000 trials for every method.

### R1-M3. Historical game-guided training archive remains to be deposited

- Axis: reproducibility and mechanism evidence
- Severity: Major
- Blocking: No for the manuscript mechanism; yes for byte-level historical provenance
- Claim pointer: Stackelberg--IBR supplies a policy prior and an auxiliary
  robust-value target, which are central to the novelty claim.
- Evidence pointer: `a2rl_paper.tex`, Eqs. `eq:prior_mse`,
  `eq:game_value_loss`, and `eq:total_loss`.
- Concern: the authors confirm that the IBR prior and robust-value head were
  active in the reported game-guided TQC study. The new
  `reference_implementation/` provides the complete executable mechanism and
  tests nonzero prior/value losses and gradients. It also separates these
  training-time modules from the standard TQC actor/critic inference export.
  The exact historical training tree, loss-weight record, and full checkpoint
  bundle are still on the remote server and are not byte-level reproducible
  from the current package.
- Resolution test: after server access is restored, archive the evaluated
  source revision and checkpoint bundle; add loss weights, IBR budgets,
  target-generation metadata, training seeds, and checksums. The reconstructed
  code remains the transparent equation-level reference, not a substitute for
  that historical archive.

### R1-M4. Baseline fairness needs an auditable tuning record

- Axis: experimental design
- Severity: Major
- Blocking: No
- Claim pointer: the comparison attributes performance differences only to
  tactical reasoning because all methods share the execution layer.
- Evidence pointer: `comparison_tables.tex`, subsection
  `Matched tactical baselines`.
- Concern: common downstream modules are documented, but baseline tuning
  budgets, compute budgets, model knowledge, failure fallbacks, and the mapping
  of each baseline output into the common corridor interface are not. A strong
  reviewer could therefore attribute part of the effect to unequal tuning or
  interface adaptation.
- Resolution test: add a matched-baseline table covering observation access,
  prediction model, update rate, horizon, optimization/learning budget,
  hyperparameter selection data, corridor adapter, and timeout/fallback rule.

### R1-M5. Practical HIL evidence lacks measured timing

- Axis: engineering validation
- Severity: Major
- Blocking: No
- Claim pointer: the target-computer HIL experiment is presented as evidence
  of practical deployability.
- Evidence pointer: Table `tab:hil_evidence` and the Discussion.
- Concern: the topology and application-representative plant are well
  documented, but the actual installed CPU/GPU/RAM, operating system, software
  versions, CAN rates and payloads, per-module runtime distribution,
  end-to-end latency, deadline-miss count, and fallback activations are absent.
  Running on the target product family is not by itself a real-time result.
- Resolution test: add the installed hardware/software configuration and
  median, 95th, 99th, and maximum cycle time for tactical policy, planner,
  MPCC, allocation, and end-to-end loop over the evaluation campaign.

### R1-M6. Statistical uncertainty cannot yet represent campaign hierarchy

- Axis: statistical rigor
- Severity: Major
- Blocking: No
- Claim pointer: the paper gives an exact binomial OSR interval, seed-level
  mean and standard deviation, and Holm-adjusted proportion tests.
- Evidence pointer: `simulation_results_refined.tex`, statistical paragraph;
  `comparison_tables.tex`, comparison and ablation inferential paragraphs.
- Concern: laps are treated as Bernoulli trials although they are nested within
  scenarios and possibly training seeds. The manuscript now labels the interval
  and count tests as descriptive, which prevents overclaiming, but the missing
  per-lap hierarchy precludes a model that supports the inferential claim.
- Resolution test: after R1-M1, report scenario-stratified effects and a
  cluster-aware interval or hierarchical model; publish the five seed-level
  rates and clarify whether the 1000-lap headline is one checkpoint or pooled
  across checkpoints.

## Minor comments

### R1-m1. Reduced model and HIL plant mass

The execution model uses 742 kg while `Eav24_default.json` specifies a 760 kg
plant. State that the former is an identified reduced model, explain the mass
difference, and report the identification/validation error. This is not a
contradiction because the manuscript already separates the internal model from
the HIL plant, but readers need the rationale.

### R1-m2. Administrative metadata

Designate a corresponding author and email. Confirm the author order,
affiliation, CRediT contributions, funding statement, acknowledgements, and
data-availability commitment. Do not infer these from the technical files.

### R1-m3. Data repository

Replace the current evidence-boundary statement with final repository DOI(s).
Include the plant configuration, campaign manifest, per-lap results, analysis
code, and figure-generation code. `DATA_REPOSITORY_PLAN.md` gives the required
record structure; a corresponding-author email alone is not a durable data
route.

### R1-m4. HIL terminology

Keep `virtual CAN` in the manuscript unless an electrical CAN interface was
physically exercised. Do not call the setup a physical CAN-bus test if the
evidence only supports a SocketCAN or simulator-level virtual bus.

## Risk and unsupported-claim audit

- Passed: the paper no longer claims that planning or control is a separate
  innovation.
- Passed: the paper does not claim formal safety, real-track validation,
  perception robustness, or multi-opponent generalization.
- Passed: `zero observed collisions` is explicitly bounded to 1000 reported
  laps and is not converted into a safety guarantee.
- Passed: simulation fidelity is supported by subsystem/configuration evidence
  and accompanied by explicit limitations rather than described as equivalent
  to track validation.
- Passed: all two-case summary values are reproducible from the included JSON
  logs. The captions disclose the single Scenario-I FSM display normalization,
  both engagement-figure boundary corrections, and the Scenario-II
  tire-envelope display mask.
- Passed: the manuscript uses the journal-required Elsevier two-column LaTeX
  layout; a separate four-bullet highlights file satisfies the 85-character
  limit; five English keywords are present; and the required generative-AI
  disclosure appears before the references.
- Optional: the journal encourages a graphical abstract, but none is supplied.
  If one is later prepared, it must not be generated or altered with generative
  AI under the current journal policy.
- Passed at aggregate level: the authors confirmed the 94.7% result and all
  table values; the JSON verifier reproduces their internal statistical logic.
- Pending archival evidence: per-lap scenario, seed, event, and timing records.
- Needs author evidence: the actual target-computer configuration and timing.
- Passed at mechanism level: the compiled manuscript's game-guided TQC
  equations now have a tested executable reference implementation, and the
  authors explicitly confirm the method--result attribution.
- Pending historical provenance: exact training-source/checkpoint deposition.

## Submission gate

The earlier fork between deleting the game-guided contribution and rerunning
the paper has been closed in favor of the author-confirmed game-guided route.
Before final submission, complete the durable per-lap and historical-code
deposit in R1-M1/R1-M3 and address R1-M2 and R1-M4 through R1-M6 in the
manuscript or source-data package. These are repository, protocol, timing, and
metadata obligations; they no longer require restructuring the paper's central
method or replacing the reported tables.
