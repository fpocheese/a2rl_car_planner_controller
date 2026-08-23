# Implementation-to-claim evidence audit

Date: 18 August 2026

This is an author-facing provenance audit, not part of the manuscript. It
separates what can be reproduced from the supplied implementation from what
still requires an author-owned experiment archive.

## 1. HIL policy identified from the supplied case logs

The metadata in the two main-text logs, `case_02.json` and `case_05.json`,
identifies the following checkpoint. The retained legacy
`case_04_trimmed.json` log identifies the same checkpoint:

`/home/uav/race24/Racecar/rl_model_backups/good_20260503_120651/current_tqc_available/phase3_1777744150_tqc_133870_steps.zip`

SHA-256:

`b28f1af84249db7d37da738aab0ab4491fdf46a48286f3b20154912896b63a6b`

The checkpoint archive and its `policy.pth` tensors establish:

| Item | Recovered value |
|---|---:|
| Algorithm class | `sb3_contrib.tqc.policies.TQCPolicy` |
| Saved updates/timesteps | 133,870 |
| Raw dynamic observation | 27 |
| Fixed-map features | 12 ego + 12 opponent |
| Feature-extractor input | 51 |
| Continuous action | 10 |
| Feature extractor | 51-256-256 |
| Actor and critic MLP | 256-256 |
| Critics | 2 |
| Quantiles per critic | 25 |
| Target atoms dropped | 2 per critic |
| Target atoms retained | 46 of 50 |
| Learning rate | 0.0003 |
| Replay capacity | 100,000 |
| Batch size | 256 |
| Discount / Polyak coefficient | 0.99 / 0.005 |
| Python / SB3 / PyTorch / Gymnasium | 3.10.0 / 2.8.0 / 2.4.0+cu124 / 1.2.3 |

The source files supporting these facts are:

- `tools/rl/a2rl_env.py` (SHA-256
  `d004e7cd858503e9a3488712916912d56c6243df4c664ecb5cead51c7709725a`)
- `tools/rl/track_prior_extractor.py` (SHA-256
  `dab03a203dac7851a2c2138486b8ab4946d650880029908fba9ec2095d762116`)
- `tools/rl/rl_action_bridge.py` (SHA-256
  `022b3c2f066cfcc6922e5799636b8313ff290de13775e3e5ed99d2ca6bf02ca9`)

The manuscript has been corrected to use 27 + 12 + 12 = 51 inputs, 46
retained target atoms, and the deployed action-projection inequalities.

The two revised representative case-summary rows are independently recomputed
by `verify_representative_cases.py`, using a common interval definition from
first `OVERTAKE` entry to the first later sample with `Delta_s < 0`.

## 2. Author-confirmed method and reconstructed executable specification

On 18 August 2026, the authors confirmed that the Stackelberg--IBR prior,
auxiliary robust-value target, game-guided TQC objective, and all aggregate
results printed in the manuscript describe the method and campaigns that were
actually run. This statement is treated as author-owned provenance; it is not
silently replaced by an inference from unrelated files.

The separate hybrid-PPO prototype found under
`src/rl-sample-mpc/tactical_acados` remains a historical implementation family
and is not presented as the evaluated source tree. Its incomplete rollout
wiring therefore no longer serves as evidence for or against the authors'
confirmed TQC training path.

To make the reported method inspectable while the historical server is
unavailable, `reference_implementation/` reconstructs the manuscript as an
executable specification:

| Manuscript claim | Reference module and executable check |
|---|---|
| Ten-dimensional bounded action and safe projection | `action.py`; projection inequalities tested in `test_reference.py` |
| Follower IBR and local robust tactical value | `game.py`; nonzero IBR prior/value target tested |
| Readiness, abort, hysteresis, and side lock | `fsm.py`; overtaking transition and lock tested |
| Footprint exclusion, width guard, and filtering | `corridor.py`; exclusion and 3 m guard tested |
| Two 25-atom critics and 46-atom target | `tqc.py`; tensor dimensions tested in `test_tqc.py` |
| Weighted policy-prior and auxiliary game-value losses | `tqc.py`; both losses and gradients tested |
| Tire-force-envelope utilization and constrained actor/target support | `tqc.py`; utilization and state-dependent action projection tested in `test_tqc.py` |

The reference implementation intentionally requires explicit callbacks or
configuration for scenario-specific utilities and numerical gates that the
manuscript does not quantify. It is not described as a byte-identical copy of
the historical source. The game-derived prior and value head are training-time
components; `inference_state_dict()` exports the standard actor/critic portion,
which reconciles the mechanism with a conventional TQC deployment archive.
The deterministic tire-force projector is configured alongside those weights
and is exercised through `constrained_policy_action()` before actor or target-
critic evaluation.

## 3. Aggregate result provenance and verification

`reported_aggregate_results.json` is now the canonical machine-readable record
for the author-confirmed headline, comparison, ablation, and seed-summary
values. `verify_reported_aggregates.py` verifies all of the following without
creating lap-level samples:

- every OSR matches its integer success count and 1000-lap denominator;
- 947/1000 gives the reported two-sided 95% exact Clopper--Pearson interval;
- all eight two-sided pooled proportion comparisons satisfy the reported
  Holm-adjusted threshold;
- every numeric entry in Tables `tab:comparison` and `tab:ablation` matches the
  JSON source.

The verifier currently reports 93.124482--96.005075% before rounding and
confirms the manuscript's 93.1--96.0% interval. The June benchmark files with
different values remain excluded because they belong to a different or
earlier record and are not the authors' confirmed source for the August tables.

The per-lap campaign archive remains on a temporarily inaccessible remote
server. It has not been fabricated or reverse-engineered. When access is
restored, the archive should add model/source identifiers, scenario and seed
assignments, event-level outcomes, timing data, and the raw-to-table pipeline
specified in `DATA_REPOSITORY_PLAN.md`.

## 4. Current decision

The method and aggregate-result narratives are now closed at the manuscript
package level through three explicitly different evidence classes:

1. **author attestation** establishes which method and aggregate values are the
   study record;
2. **included source artifacts and logs** establish the deployment dimensions,
   representative cases, and plant configuration;
3. **reconstructed executable code and aggregate verification** establish that
   the equations are implementable and the printed statistics are internally
   reproducible.

This closes the earlier method-deletion fork: the game-guided claims are
retained and have an executable counterpart. It does not turn unavailable
per-lap files into public source data. Final repository deposition, exact
historical source/checkpoint archival, administrative metadata, and the still
unreported timing/protocol details remain author-side submission actions.
